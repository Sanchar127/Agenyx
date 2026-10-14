package recipe

import (
	"errors"
	"fmt"
)

const GatewayRecipeKind = "GatewayRecipe"

type GatewaySpec struct {
	RateLimit GatewayRateLimitSpec `yaml:"rateLimit"`
	Request   GatewayRequestSpec   `yaml:"request"`
}

type GatewayRateLimitSpec struct {
	RequestsPerSecond int `yaml:"requestsPerSecond"`
	Burst             int `yaml:"burst"`
}

type GatewayRequestSpec struct {
	MaxBodyBytes int64 `yaml:"maxBodyBytes"`
}

func (s GatewaySpec) Validate() error {
	if s.RateLimit.RequestsPerSecond <= 0 {
		return errors.New("rateLimit.requestsPerSecond must be greater than zero")
	}

	if s.RateLimit.Burst <= 0 {
		return errors.New("rateLimit.burst must be greater than zero")
	}

	if s.Request.MaxBodyBytes <= 0 {
		return errors.New("request.maxBodyBytes must be greater than zero")
	}

	// Protect against accidental configuration of an excessively large limit.
	const maxAllowedBodyBytes int64 = 1 << 30 // 1 GiB

	if s.Request.MaxBodyBytes > maxAllowedBodyBytes {
		return fmt.Errorf(
			"request.maxBodyBytes must not exceed %d",
			maxAllowedBodyBytes,
		)
	}

	return nil
}
