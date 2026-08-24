// Package registry provides the model registry and model metadata operations.
package registry

import (
	"strings"

	"github.com/sanchar127/agenyx/pkg/router"
)

// Model is the internal representation of a registered model.
type Model = router.Model

// SupportsCapability reports whether the model provides the requested
// capability. Capability matching is case-insensitive.
func SupportsCapability(model Model, capability string) bool {
	capability = strings.TrimSpace(strings.ToLower(capability))

	if capability == "" {
		return false
	}

	for _, candidate := range model.Capabilities {
		if strings.EqualFold(strings.TrimSpace(candidate), capability) {
			return true
		}
	}

	return false
}
