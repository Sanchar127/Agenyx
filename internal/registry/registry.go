package registry

import (
	"fmt"
	"sort"
	"strings"
	"sync"

	"github.com/sanchar127/agenyx/pkg/router"
)

// Registry stores the models available to the routing engine.
//
// Registry is safe for concurrent reads and writes.
type Registry struct {
	mu     sync.RWMutex
	models map[string]router.Model
}

// New creates an empty model registry.
func New() *Registry {
	return &Registry{
		models: make(map[string]router.Model),
	}
}

// Register adds or replaces a model.
//
// Model names are unique identifiers within a registry.
func (r *Registry) Register(model router.Model) error {
	if err := validateModel(model); err != nil {
		return err
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	r.models[model.Name] = model

	return nil
}

// Get retrieves a model by name.
func (r *Registry) Get(name string) (router.Model, bool) {
	name = strings.TrimSpace(name)

	if name == "" {
		return router.Model{}, false
	}

	r.mu.RLock()
	defer r.mu.RUnlock()

	model, ok := r.models[name]

	return model, ok
}

// Remove removes a model from the registry.
func (r *Registry) Remove(name string) bool {
	name = strings.TrimSpace(name)

	if name == "" {
		return false
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if _, ok := r.models[name]; !ok {
		return false
	}

	delete(r.models, name)

	return true
}

// List returns all registered models.
//
// The returned slice is independent from the registry and may safely
// be modified by the caller.
func (r *Registry) List() []router.Model {
	r.mu.RLock()
	defer r.mu.RUnlock()

	models := make([]router.Model, 0, len(r.models))

	for _, model := range r.models {
		models = append(models, model)
	}

	sort.Slice(models, func(i, j int) bool {
		return models[i].Name < models[j].Name
	})

	return models
}

// Enabled returns all currently enabled models.
func (r *Registry) Enabled() []router.Model {
	r.mu.RLock()
	defer r.mu.RUnlock()

	models := make([]router.Model, 0, len(r.models))

	for _, model := range r.models {
		if model.Enabled {
			models = append(models, model)
		}
	}

	sort.Slice(models, func(i, j int) bool {
		return models[i].Name < models[j].Name
	})

	return models
}

func validateModel(model router.Model) error {
	if strings.TrimSpace(model.Name) == "" {
		return fmt.Errorf("model name cannot be empty")
	}

	if strings.TrimSpace(model.Provider) == "" {
		return fmt.Errorf("provider cannot be empty")
	}

	if model.ContextWindow < 0 {
		return fmt.Errorf("context window cannot be negative")
	}

	return nil
}
