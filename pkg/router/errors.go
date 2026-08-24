// Package router defines the public semantic routing API and contracts.
package router

import "errors"

var (
	// ErrInvalidRequest indicates that the routing request is malformed.
	ErrInvalidRequest = errors.New("invalid routing request")

	// ErrNoCandidates indicates that no eligible model could be selected.
	ErrNoCandidates = errors.New("no eligible models found")

	// ErrModelNotFound indicates that an explicitly requested model
	// does not exist in the registry.
	ErrModelNotFound = errors.New("requested model not found")

	// ErrRoutingFailed indicates an unexpected routing failure.
	ErrRoutingFailed = errors.New("routing failed")
)
