// Command agenyx is the entrypoint for the Agenyx service.
package main

import (
	"log"
	"net/http"

	"github.com/sanchar127/agenyx/internal/httpapi"
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
			log.Fatalf("register model %q: %v", model.Name, err)
		}
	}

	store := session.NewMemoryStore()

	engine := internalrouter.New(
		reg,
		[]router.Strategy{
			strategy.NewCapabilityStrategy(),
		},
		scoring.NewPriorityScorer(0.01),
		store,
		internalrouter.SessionConfig{
			AffinityWeight:  0.10,
			SwitchThreshold: 0.20,
		},
	)

	api := httpapi.New(engine, reg)

	mux := http.NewServeMux()
	api.RegisterRoutes(mux)

	server := &http.Server{
		Addr:    ":8080",
		Handler: mux,
	}

	log.Printf("agenyx semantic router listening on %s", server.Addr)

	if err := server.ListenAndServe(); err != nil &&
		err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
