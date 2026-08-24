// Package router implements the internal semantic routing engine.
package router

import (
	"context"
	"sort"
	"strings"
	"time"

	"github.com/sanchar127/agenyx/internal/registry"
	"github.com/sanchar127/agenyx/internal/scoring"
	"github.com/sanchar127/agenyx/pkg/router"
)

// SessionConfig controls session-aware model affinity.
type SessionConfig struct {
	AffinityWeight  float64
	SwitchThreshold float64
}

// Engine is the stateless routing engine.
//
// All mutable session state is externalized into SessionStore.
type Engine struct {
	registry   *registry.Registry
	strategies []router.Strategy
	scorer     scoring.Scorer
	sessions   router.SessionStore
	sessionCfg SessionConfig
}

// New creates a routing engine.
func New(
	reg *registry.Registry,
	strategies []router.Strategy,
	scorer scoring.Scorer,
	sessions router.SessionStore,
	sessionCfg SessionConfig,
) *Engine {
	return &Engine{
		registry:   reg,
		strategies: append([]router.Strategy(nil), strategies...),
		scorer:     scorer,
		sessions:   sessions,
		sessionCfg: sessionCfg,
	}
}

// Route evaluates the request and returns a model decision.
func (e *Engine) Route(
	ctx context.Context,
	request router.Request,
) (router.Decision, error) {
	if err := validateRequest(request); err != nil {
		return router.Decision{}, err
	}

	if err := ctx.Err(); err != nil {
		return router.Decision{}, err
	}

	candidates := filterCandidates(
		e.registry.Enabled(),
		request,
	)

	if len(candidates) == 0 {
		return router.Decision{}, router.ErrNoCandidates
	}

	results, strategyName, err := e.evaluate(
		ctx,
		request,
		candidates,
	)
	if err != nil {
		return router.Decision{}, err
	}

	if len(results) == 0 {
		return router.Decision{}, router.ErrNoCandidates
	}

	decisionCandidates := make(
		[]router.Candidate,
		0,
		len(results),
	)

	var currentSession router.SessionState
	var hasSession bool

	if request.SessionID != "" && e.sessions != nil {
		currentSession, hasSession, err =
			e.sessions.Get(
				ctx,
				request.SessionID,
			)

		if err != nil {
			return router.Decision{}, err
		}
	}

	for _, result := range results {
		score := result.Score

		if e.scorer != nil {
			score = e.scorer.Score(
				result.Model,
				score,
			)
		}

		if hasSession &&
			currentSession.CurrentModel == result.Model.Name {
			score += e.sessionCfg.AffinityWeight
		}

		decisionCandidates = append(
			decisionCandidates,
			router.Candidate{
				Model: result.Model,
				Score: score,
			},
		)
	}

	sortCandidates(decisionCandidates)

	selected := decisionCandidates[0]

	// Prevent unnecessary model switching. The current model is retained
	// unless the best alternative clears the configured switch threshold.
	if hasSession &&
		currentSession.CurrentModel != "" &&
		currentSession.CurrentModel != selected.Model.Name {
		if current := findCandidate(
			decisionCandidates,
			currentSession.CurrentModel,
		); current != nil {
			if selected.Score <
				current.Score+e.sessionCfg.SwitchThreshold {
				selected = *current
			}
		}
	}

	decision := router.Decision{
		Model:      selected.Model.Name,
		Provider:   selected.Model.Provider,
		Score:      selected.Score,
		Strategy:   strategyName,
		Candidates: decisionCandidates,
	}

	if request.SessionID != "" && e.sessions != nil {
		if err := e.updateSession(
			ctx,
			request.SessionID,
			currentSession,
			hasSession,
			decision,
		); err != nil {
			return router.Decision{}, err
		}
	}

	return decision, nil
}

func (e *Engine) evaluate(
	ctx context.Context,
	request router.Request,
	candidates []router.Model,
) ([]router.CandidateScore, string, error) {
	for _, strat := range e.strategies {
		if err := ctx.Err(); err != nil {
			return nil, "", err
		}

		results, err := strat.Evaluate(
			ctx,
			request,
			candidates,
		)
		if err != nil {
			return nil, "", err
		}

		if len(results) > 0 {
			return results, strat.Name(), nil
		}
	}

	return nil, "", router.ErrNoCandidates
}

func (e *Engine) updateSession(
	ctx context.Context,
	sessionID string,
	current router.SessionState,
	exists bool,
	decision router.Decision,
) error {
	next := current

	if !exists {
		next = router.SessionState{
			SessionID:  sessionID,
			ModelTurns: make(map[string]int64),
		}
	}

	if next.ModelTurns == nil {
		next.ModelTurns = make(map[string]int64)
	}

	if next.CurrentModel != "" &&
		next.CurrentModel != decision.Model {
		next.SwitchCount++
	}

	next.CurrentModel = decision.Model
	next.TurnCount++
	next.ModelTurns[decision.Model]++
	next.LastDecision = decision.Strategy
	next.LastSeen = time.Now().UTC()

	return e.sessions.CompareAndSwap(
		ctx,
		sessionID,
		current.Version,
		next,
	)
}

func validateRequest(request router.Request) error {
	if len(request.Messages) == 0 {
		return router.ErrInvalidRequest
	}

	for _, message := range request.Messages {
		if strings.TrimSpace(message.Role) == "" {
			return router.ErrInvalidRequest
		}
	}

	return nil
}

func filterCandidates(
	candidates []router.Model,
	request router.Request,
) []router.Model {
	result := make([]router.Model, 0, len(candidates))

	for _, model := range candidates {
		if !providerAllowed(
			model.Provider,
			request.Constraints.AllowedProviders,
		) {
			continue
		}

		if !modelAllowed(
			model.Name,
			request.Constraints.AllowedModels,
		) {
			continue
		}

		if request.Constraints.MinContextWindow > 0 &&
			model.ContextWindow <
				request.Constraints.MinContextWindow {
			continue
		}

		if !capabilitiesSatisfied(
			model,
			request.Constraints.RequiredCapabilities,
		) {
			continue
		}

		result = append(result, model)
	}

	return result
}

func providerAllowed(
	provider string,
	allowed []string,
) bool {
	if len(allowed) == 0 {
		return true
	}

	for _, candidate := range allowed {
		if strings.EqualFold(
			strings.TrimSpace(candidate),
			provider,
		) {
			return true
		}
	}

	return false
}

func modelAllowed(
	model string,
	allowed []string,
) bool {
	if len(allowed) == 0 {
		return true
	}

	for _, candidate := range allowed {
		if strings.TrimSpace(candidate) == model {
			return true
		}
	}

	return false
}

func capabilitiesSatisfied(
	model router.Model,
	required []string,
) bool {
	for _, capability := range required {
		if !registry.SupportsCapability(
			model,
			capability,
		) {
			return false
		}
	}

	return true
}

func sortCandidates(
	candidates []router.Candidate,
) {
	sort.SliceStable(
		candidates,
		func(i, j int) bool {
			if candidates[i].Score != candidates[j].Score {
				return candidates[i].Score >
					candidates[j].Score
			}

			if candidates[i].Model.Priority !=
				candidates[j].Model.Priority {
				return candidates[i].Model.Priority >
					candidates[j].Model.Priority
			}

			return candidates[i].Model.Name <
				candidates[j].Model.Name
		},
	)
}

func findCandidate(
	candidates []router.Candidate,
	model string,
) *router.Candidate {
	for i := range candidates {
		if candidates[i].Model.Name == model {
			return &candidates[i]
		}
	}

	return nil
}
