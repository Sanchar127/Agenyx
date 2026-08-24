// Package main provides the semantic router demonstration executable.
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/sanchar127/agenyx/internal/registry"
	internalrouter "github.com/sanchar127/agenyx/internal/router"
	"github.com/sanchar127/agenyx/internal/scoring"
	"github.com/sanchar127/agenyx/internal/session"
	"github.com/sanchar127/agenyx/internal/strategy"
	"github.com/sanchar127/agenyx/pkg/router"
)

func main() {
	reg := registry.New()

	models := []router.Model{
		{
			Name:          "qwen2.5:7b",
			Provider:      "ollama",
			Capabilities:  []string{"general", "coding"},
			ContextWindow: 32768,
			Priority:      10,
			Enabled:       true,
		},
		{
			Name:          "llama3.2",
			Provider:      "ollama",
			Capabilities:  []string{"general"},
			ContextWindow: 8192,
			Priority:      5,
			Enabled:       true,
		},
	}

	for _, model := range models {
		if err := reg.Register(model); err != nil {
			log.Fatal(err)
		}
	}

	store := session.NewMemoryStore()

	scorer := scoring.NewPriorityScorer(0.01)

	strategies := []router.Strategy{
		strategy.NewCapabilityStrategy(),
	}

	engine := internalrouter.New(
		reg,
		strategies,
		scorer,
		store,
		internalrouter.SessionConfig{
			AffinityWeight:  0.10,
			SwitchThreshold: 0.20,
		},
	)

	ctx := context.Background()

	request := router.Request{
		SessionID: "demo-session",
		Task:      "coding",
		Messages: []router.Message{
			{
				Role:    "user",
				Content: "Write a Go HTTP server",
			},
		},
		Constraints: router.Constraints{
			RequiredCapabilities: []string{"coding"},
		},
	}

	decision, err := engine.Route(ctx, request)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf(
		"model=%s provider=%s score=%.4f strategy=%s\n",
		decision.Model,
		decision.Provider,
		decision.Score,
		decision.Strategy,
	)

	fmt.Println("semantic router running successfully")
}
