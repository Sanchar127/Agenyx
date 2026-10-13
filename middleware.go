package main

import (
	"crypto/rand"
	"encoding/hex"
	"log"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Middleware func(http.Handler) http.Handler

func chain(handler http.Handler, middleware ...Middleware) http.Handler {
	for i := len(middleware) - 1; i >= 0; i-- {
		handler = middleware[i](handler)
	}

	return handler
}

func requestIDMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := make([]byte, 16)

		if _, err := rand.Read(id); err != nil {
			http.Error(w, "internal server error", http.StatusInternalServerError)
			return
		}

		requestID := hex.EncodeToString(id)

		r.Header.Set("X-Request-ID", requestID)
		w.Header().Set("X-Request-ID", requestID)

		next.ServeHTTP(w, r)
	})
}

func securityHeadersMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("Referrer-Policy", "no-referrer")

		next.ServeHTTP(w, r)
	})
}

const maxRequestBodyBytes int64 = 1 << 20 // 1 MiB

func requestSizeMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Body == nil {
			next.ServeHTTP(w, r)
			return
		}

		// Limit how much data can be read from the request body.
		r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)

		// Reject requests that declare a body larger than the limit.
		if r.ContentLength > maxRequestBodyBytes {
			writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{
				"error": "request body too large",
			})
			return
		}

		next.ServeHTTP(w, r)
	})
}

type responseRecorder struct {
	http.ResponseWriter
	status int
	bytes  int
}

func (w *responseRecorder) WriteHeader(status int) {
	if w.status != 0 {
		return
	}

	w.status = status
	w.ResponseWriter.WriteHeader(status)
}

// Unwrap exposes the original writer to http.ResponseController.
func (w *responseRecorder) Unwrap() http.ResponseWriter {
	return w.ResponseWriter
}

// Flush forwards flushes so streaming responses can reach the client.
func (w *responseRecorder) Flush() {
	if w.status == 0 {
		w.WriteHeader(http.StatusOK)
	}
	if flusher, ok := w.ResponseWriter.(http.Flusher); ok {
		flusher.Flush()
	}
}

func (w *responseRecorder) Write(data []byte) (int, error) {
	if w.status == 0 {
		w.WriteHeader(http.StatusOK)
	}

	n, err := w.ResponseWriter.Write(data)
	w.bytes += n

	return n, err
}

func accessLogMiddleware(logger *log.Logger) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			recorder := &responseRecorder{ResponseWriter: w}

			next.ServeHTTP(recorder, r)

			status := recorder.status
			if status == 0 {
				status = http.StatusOK
			}

			logger.Printf(
				`{"time":%q,"request_id":%q,"remote_addr":%q,"method":%q,"uri":%q,"status":%d,"request_time_ms":%d,"bytes":%d,"user_agent":%q}`,
				time.Now().UTC().Format(time.RFC3339Nano),
				r.Header.Get("X-Request-ID"),
				clientIP(r),
				r.Method,
				r.URL.RequestURI(),
				status,
				time.Since(start).Milliseconds(),
				recorder.bytes,
				r.UserAgent(),
			)
		})
	}
}

type bucket struct {
	tokens     float64
	lastUpdate time.Time
}

type RateLimiter struct {
	mu       sync.Mutex
	buckets  map[string]*bucket
	rate     float64
	capacity float64
}

func NewRateLimiter(rate, burst int) *RateLimiter {
	return &RateLimiter{
		buckets:  make(map[string]*bucket),
		rate:     float64(rate),
		capacity: float64(burst),
	}
}

func (l *RateLimiter) allow(ip string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := time.Now()

	b, ok := l.buckets[ip]
	if !ok {
		b = &bucket{
			tokens:     l.capacity,
			lastUpdate: now,
		}
		l.buckets[ip] = b
	}

	elapsed := now.Sub(b.lastUpdate).Seconds()
	b.tokens += elapsed * l.rate

	if b.tokens > l.capacity {
		b.tokens = l.capacity
	}

	b.lastUpdate = now

	if b.tokens < 1 {
		return false
	}

	b.tokens--
	return true
}

func (l *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/v1/") {
			next.ServeHTTP(w, r)
			return
		}

		if !l.allow(clientIP(r)) {
			w.Header().Set("Retry-After", strconv.Itoa(1))
			http.Error(w, "rate limit exceeded", http.StatusTooManyRequests)
			return
		}

		next.ServeHTTP(w, r)
	})
}
