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
			return fmt.Errorf("network rule host cannot be empty")
		}

		if rule.Port == 0 {
			return fmt.Errorf(
				"network rule port cannot be 0 for host %q",
				rule.Host,
			)
		}

		key := fmt.Sprintf("%s:%d", rule.Host, rule.Port)

		if _, exists := seen[key]; exists {
			return fmt.Errorf(
				"duplicate network rule: %s",
				key,
			)
		}

		seen[key] = struct{}{}
	}

	return nil
}
