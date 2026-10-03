package domain

import "fmt"

type NetworkRule struct {
	Host string
	Port uint16
}

type NetworkPolicy struct {
	Enabled     bool
	EgressRules []NetworkRule
}

func (p NetworkPolicy) Validate() error {
	seen := make(map[string]struct{}, len(p.EgressRules))

	for _, rule := range p.EgressRules {
		if rule.Host == "" {
			return fmt.Errorf("%w: network rule host cannot be empty", ErrInvalidInput)
		}

		if rule.Port == 0 {
			return fmt.Errorf(
				"%w: network rule port cannot be 0 for host %q",
				ErrInvalidInput,
				rule.Host,
			)
		}

		key := fmt.Sprintf("%s:%d", rule.Host, rule.Port)

		if _, exists := seen[key]; exists {
			return fmt.Errorf(
				"%w: duplicate network rule: %s",
				ErrInvalidInput,
				key,
			)
		}

		seen[key] = struct{}{}
	}

	return nil
}
