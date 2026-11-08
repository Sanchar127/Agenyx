package gateway

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// sessionCookieName is the name of the cookie that holds the session token.
const sessionCookieName = "agenyx_session"

// sessionTokenLength is the number of random bytes used for a session token.
const sessionTokenLength = 32

// SessionStore holds active sessions in memory. In production this should
// be backed by Valkey/Redis for horizontal scaling.
type SessionStore struct {
	mu         sync.RWMutex
	sessions   map[string]*Session
	sessionTTL time.Duration
}

// Session represents an authenticated user session.
type Session struct {
	Token     string
	Provider  string
	Subject   string // The OAuth provider's subject/user ID
	Email     string
	Name      string
	CreatedAt time.Time
	ExpiresAt time.Time
}

// NewSessionStore creates a session store with the given TTL.
func NewSessionStore(ttl time.Duration) *SessionStore {
	s := &SessionStore{
		sessions:   make(map[string]*Session),
		sessionTTL: ttl,
	}

	// Run a periodic cleanup goroutine.
	go s.cleanup()

	return s
}

// cleanup removes expired sessions every minute.
func (s *SessionStore) cleanup() {
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		s.mu.Lock()
		now := time.Now()
		for token, session := range s.sessions {
			if now.After(session.ExpiresAt) {
				delete(s.sessions, token)
			}
		}
		s.mu.Unlock()
	}
}

// Create creates a new session and returns its token.
func (s *SessionStore) Create(provider, subject, email, name string) string {
	token := s.newToken()

	session := &Session{
		Token:     token,
		Provider:  provider,
		Subject:   subject,
		Email:     email,
		Name:      name,
		CreatedAt: time.Now(),
		ExpiresAt: time.Now().Add(s.sessionTTL),
	}

	s.mu.Lock()
	s.sessions[token] = session
	s.mu.Unlock()

	return token
}

// Get returns the session for the given token, or nil if not found/expired.
func (s *SessionStore) Get(token string) *Session {
	s.mu.RLock()
	defer s.mu.RUnlock()

	session, ok := s.sessions[token]
	if !ok {
		return nil
	}

	if time.Now().After(session.ExpiresAt) {
		return nil
	}

	return session
}

// Delete removes a session.
func (s *SessionStore) Delete(token string) {
	s.mu.Lock()
	delete(s.sessions, token)
	s.mu.Unlock()
}

// newToken generates a cryptographically random session token.
func (s *SessionStore) newToken() string {
	b := make([]byte, sessionTokenLength)
	if _, err := rand.Read(b); err != nil {
		// Fallback to a less secure token if rand fails.
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b)
}

// oauthProviderConfig holds the OAuth endpoints for a provider.
type oauthProviderConfig struct {
	tokenURL     string
	userInfoURL  string
	clientID     string
	clientSecret string
	scopes       string
	authStyle    string // "query" or "body" for client credentials
}

// oauthProviders holds the configured OAuth providers.
var oauthProviders = map[string]oauthProviderConfig{}

// registerOAuthProvider configures an OAuth provider.
func registerOAuthProvider(name, tokenURL, userInfoURL, clientID, clientSecret, scopes string) {
	oauthProviders[name] = oauthProviderConfig{
		tokenURL:     tokenURL,
		userInfoURL:  userInfoURL,
		clientID:     clientID,
		clientSecret: clientSecret,
		scopes:       scopes,
	}
}

// oauthTokenResponse is the response from an OAuth token endpoint.
type oauthTokenResponse struct {
	AccessToken  string `json:"access_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"`
	RefreshToken string `json:"refresh_token"`
	IDToken      string `json:"id_token"`
	Error        string `json:"error"`
	ErrorDesc    string `json:"error_description"`
}

// exchangeCode exchanges an authorization code for an access token.
func exchangeCode(providerName, code, redirectURI string) (*oauthTokenResponse, error) {
	cfg, ok := oauthProviders[providerName]
	if !ok {
		return nil, fmt.Errorf("unknown OAuth provider: %s", providerName)
	}

	data := url.Values{}
	data.Set("grant_type", "authorization_code")
	data.Set("code", code)
	data.Set("redirect_uri", redirectURI)
	data.Set("client_id", cfg.clientID)

	if cfg.clientSecret != "" {
		data.Set("client_secret", cfg.clientSecret)
	}

	req, err := http.NewRequest(
		http.MethodPost,
		cfg.tokenURL,
		strings.NewReader(data.Encode()),
	)
	if err != nil {
		return nil, fmt.Errorf("create token request: %w", err)
	}

	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("token request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read token response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		var errResp oauthTokenResponse
		if jsonErr := json.Unmarshal(body, &errResp); jsonErr == nil {
			return nil, fmt.Errorf(
				"token exchange failed: %s %s",
				errResp.Error,
				errResp.ErrorDesc,
			)
		}
		return nil, fmt.Errorf(
			"token exchange failed with status %d: %s",
			resp.StatusCode,
			string(body),
		)
	}

	var tokenResp oauthTokenResponse
	if err := json.Unmarshal(body, &tokenResp); err != nil {
		return nil, fmt.Errorf("parse token response: %w", err)
	}

	return &tokenResp, nil
}

// fetchUserInfo calls the provider's userinfo endpoint and returns the user's
// subject, email, and name.
func fetchUserInfo(providerName, accessToken string) (subject, email, name string, err error) {
	cfg, ok := oauthProviders[providerName]
	if !ok {
		return "", "", "", fmt.Errorf("unknown OAuth provider: %s", providerName)
	}

	req, err := http.NewRequest(http.MethodGet, cfg.userInfoURL, nil)
	if err != nil {
		return "", "", "", fmt.Errorf("create userinfo request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+accessToken)
	req.Header.Set("Accept", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", "", "", fmt.Errorf("userinfo request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", "", "", fmt.Errorf("read userinfo response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return "", "", "", fmt.Errorf(
			"userinfo request failed with status %d: %s",
			resp.StatusCode,
			string(body),
		)
	}

	// Google and GitHub return different shapes. Parse common fields.
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(body, &raw); err != nil {
		return "", "", "", fmt.Errorf("parse userinfo: %w", err)
	}

	// Extract subject (Google: "sub", GitHub: "id")
	if v, ok := raw["sub"]; ok {
		subject = stringValue(v)
	} else if v, ok := raw["id"]; ok {
		subject = stringValue(v)
	}

	// Extract email
	if v, ok := raw["email"]; ok {
		email = stringValue(v)
	}

	// Extract name
	if v, ok := raw["name"]; ok {
		name = stringValue(v)
	} else if v, ok := raw["login"]; ok {
		name = stringValue(v) // GitHub uses "login"
	}

	return subject, email, name, nil
}

// stringValue extracts a string from a json.RawMessage.
func stringValue(raw json.RawMessage) string {
	var s string
	if err := json.Unmarshal(raw, &s); err != nil {
		return ""
	}
	return s
}

// writeSessionCookie sets the session cookie on the response.
func writeSessionCookie(w http.ResponseWriter, token string, secure bool) {
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		Secure:   secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   int((24 * time.Hour).Seconds()),
	})
}

// clearSessionCookie removes the session cookie.
func clearSessionCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   false,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
	})
}

// readSessionToken reads the session token from the request cookie.
func readSessionToken(r *http.Request) string {
	cookie, err := r.Cookie(sessionCookieName)
	if err != nil {
		return ""
	}
	return cookie.Value
}

// sessionMiddleware validates the session cookie and adds the session to the
// request context. If no valid session exists, it returns 401.
func (s *SessionStore) sessionMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := readSessionToken(r)
		if token == "" {
			writeJSON(w, http.StatusUnauthorized, map[string]string{
				"error": "unauthorized",
			})
			return
		}

		session := s.Get(token)
		if session == nil {
			writeJSON(w, http.StatusUnauthorized, map[string]string{
				"error": "unauthorized",
			})
			return
		}

		// Store session in request context for downstream handlers.
		ctx := context.WithValue(r.Context(), sessionKey{}, session)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// sessionKey is an unexported type for context keys to avoid collisions.
type sessionKey struct{}

// getSession returns the session stored in the request context, or nil.
func getSession(r *http.Request) *Session {
	session, _ := r.Context().Value(sessionKey{}).(*Session)
	return session
}
