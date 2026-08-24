package strategy

import "github.com/sanchar127/agenyx/pkg/router"

// Strategy is an alias to the public routing strategy contract.
//
// Built-in strategies remain internal while the extension point remains
// part of the stable public API.
type Strategy = router.Strategy

// CandidateScore is retained as an alias for internal implementations.
type CandidateScore = router.CandidateScore
