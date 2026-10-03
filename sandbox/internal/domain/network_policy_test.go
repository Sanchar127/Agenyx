package domain

import "testing"

func TestNetworkPolicy(t *testing.T) {
	policy := NetworkPolicy{
		Enabled: true,
		EgressRules: []NetworkRule{
			{
				Host: "api.github.com",
				Port: 443,
			},
			{
				Host: "pypi.org",
				Port: 443,
			},
		},
	}

	if !policy.Enabled {
		t.Fatal("expected network policy to be enabled")
	}

	if len(policy.EgressRules) != 2 {
		t.Fatalf(
			"expected 2 egress rules, got %d",
			len(policy.EgressRules),
		)
	}

	if policy.EgressRules[0].Host != "api.github.com" {
		t.Fatalf(
			"expected first host api.github.com, got %q",
			policy.EgressRules[0].Host,
		)
	}

	if policy.EgressRules[0].Port != 443 {
		t.Fatalf(
			"expected first port 443, got %d",
			policy.EgressRules[0].Port,
		)
	}
}

func TestNetworkPolicyValidate(t *testing.T) {
	policy := NetworkPolicy{
		Enabled: true,
		EgressRules: []NetworkRule{
			{
				Host: "api.github.com",
				Port: 443,
			},
			{
				Host: "pypi.org",
				Port: 443,
			},
		},
	}

	if err := policy.Validate(); err != nil {
		t.Fatalf("expected valid network policy, got error: %v", err)
	}
}

func TestNetworkPolicyValidateRejectsInvalidRules(t *testing.T) {
	tests := []struct {
		name   string
		policy NetworkPolicy
	}{
		{
			name: "empty host",
			policy: NetworkPolicy{
				Enabled: true,
				EgressRules: []NetworkRule{
					{
						Host: "",
						Port: 443,
					},
				},
			},
		},
		{
			name: "zero port",
			policy: NetworkPolicy{
				Enabled: true,
				EgressRules: []NetworkRule{
					{
						Host: "api.github.com",
						Port: 0,
					},
				},
			},
		},
		{
			name: "duplicate rule",
			policy: NetworkPolicy{
				Enabled: true,
				EgressRules: []NetworkRule{
					{
						Host: "api.github.com",
						Port: 443,
					},
					{
						Host: "api.github.com",
						Port: 443,
					},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := tt.policy.Validate(); err == nil {
				t.Fatal("expected validation error, got nil")
			}
		})
	}
}
