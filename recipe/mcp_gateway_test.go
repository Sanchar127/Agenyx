package recipe

import (
	"strings"
	"testing"
)

func TestLoadMCPGatewayDefaultRecipe(t *testing.T) {
	path := "../recipes/mcp-gateway/default.yaml"

	spec, err := LoadMCPGatewaySpec(path)
	if err != nil {
		t.Fatalf("LoadMCPGatewaySpec() error = %v", err)
	}

	if spec.Server.Name != "agenyx-mcp-gateway" {
		t.Errorf("server.name = %q, want agenyx-mcp-gateway", spec.Server.Name)
	}

	if spec.Server.ListenAddress != "0.0.0.0:8081" {
		t.Errorf("server.listenAddress = %q, want 0.0.0.0:8081", spec.Server.ListenAddress)
	}

	if spec.Security.Authorization.DefaultPolicy != "deny" {
		t.Errorf("defaultPolicy = %q, want deny", spec.Security.Authorization.DefaultPolicy)
	}

	if len(spec.Upstreams) != 0 {
		t.Errorf("upstreams count = %d, want 0", len(spec.Upstreams))
	}
}

func TestLoadMCPGatewayRejectsWrongKind(t *testing.T) {
	path := writeRecipe(t, `
apiVersion: agenyx.ai/v1alpha1
kind: GatewayRecipe
metadata:
  name: test
spec:
  server:
    name: test
`)

	_, err := LoadMCPGatewaySpec(path)
	if err == nil {
		t.Fatal("expected an error for the wrong recipe kind")
	}

	if !strings.Contains(err.Error(), MCPGatewayRecipeKind) {
		t.Errorf("error = %q, want mention of %q", err, MCPGatewayRecipeKind)
	}
}

func TestLoadMCPGatewayRejectsUnknownSpecField(t *testing.T) {
	path := writeRecipe(t, `
apiVersion: agenyx.ai/v1alpha1
kind: MCPGatewayRecipe
metadata:
  name: test
spec:
  unknownSetting: true
`)

	_, err := LoadMCPGatewaySpec(path)
	if err == nil {
		t.Fatal("expected an error for an unknown spec field")
	}

	if !strings.Contains(err.Error(), "unknownSetting") {
		t.Errorf("error = %q, want mention of unknownSetting", err)
	}
}

func TestMCPGatewaySpecRejectsInvalidConfiguration(t *testing.T) {
	valid := MCPGatewaySpec{
		Server: MCPGatewayServerSpec{
			Name:          "test",
			ListenAddress: "127.0.0.1:8081",
			Transport:     MCPTransportStreamableHTTP,
			Endpoint:      "/mcp",
		},
		Discovery: MCPGatewayDiscoverySpec{
			RefreshInterval: "60s",
			CacheTools:      true,
		},
		Security: MCPGatewaySecuritySpec{
			Authentication: MCPGatewayAuthenticationSpec{
				Enabled:  true,
				Mode:     "bearer",
				TokenEnv: "AGENYX_MCP_GATEWAY_TOKEN",
			},
			Authorization: MCPGatewayAuthorizationSpec{
				DefaultPolicy: "deny",
			},
		},
		Execution: MCPGatewayExecutionSpec{
			Timeout:            "30s",
			MaxConcurrentCalls: 100,
		},
		Limits: MCPGatewayLimitsSpec{
			MaxArgumentsBytes: 1 << 20,
			MaxResultBytes:    4 << 20,
		},
	}

	tests := []struct {
		name   string
		mutate func(*MCPGatewaySpec)
	}{
		{
			name: "empty server name",
			mutate: func(s *MCPGatewaySpec) {
				s.Server.Name = ""
			},
		},
		{
			name: "invalid listen address",
			mutate: func(s *MCPGatewaySpec) {
				s.Server.ListenAddress = "not-an-address"
			},
		},
		{
			name: "unsupported transport",
			mutate: func(s *MCPGatewaySpec) {
				s.Server.Transport = "stdio"
			},
		},
		{
			name: "invalid endpoint",
			mutate: func(s *MCPGatewaySpec) {
				s.Server.Endpoint = "mcp"
			},
		},
		{
			name: "invalid discovery interval",
			mutate: func(s *MCPGatewaySpec) {
				s.Discovery.RefreshInterval = "not-a-duration"
			},
		},
		{
			name: "authentication missing token environment variable",
			mutate: func(s *MCPGatewaySpec) {
				s.Security.Authentication.TokenEnv = ""
			},
		},
		{
			name: "authorization must deny by default",
			mutate: func(s *MCPGatewaySpec) {
				s.Security.Authorization.DefaultPolicy = "allow"
			},
		},
		{
			name: "zero execution timeout",
			mutate: func(s *MCPGatewaySpec) {
				s.Execution.Timeout = "0s"
			},
		},
		{
			name: "zero concurrency",
			mutate: func(s *MCPGatewaySpec) {
				s.Execution.MaxConcurrentCalls = 0
			},
		},
		{
			name: "excessive argument limit",
			mutate: func(s *MCPGatewaySpec) {
				s.Limits.MaxArgumentsBytes = 17 << 20
			},
		},
		{
			name: "excessive result limit",
			mutate: func(s *MCPGatewaySpec) {
				s.Limits.MaxResultBytes = 65 << 20
			},
		},
		{
			name: "duplicate upstream names",
			mutate: func(s *MCPGatewaySpec) {
				s.Upstreams = []MCPGatewayUpstreamSpec{
					{Name: "tools"},
					{Name: "tools"},
				}
			},
		},
		{
			name: "enabled upstream without tool policy",
			mutate: func(s *MCPGatewaySpec) {
				s.Upstreams = []MCPGatewayUpstreamSpec{
					{
						Name:    "tools",
						Enabled: true,
						Connection: MCPGatewayConnectionSpec{
							Transport: MCPTransportStreamableHTTP,
							URL:       "https://mcp.example.com/mcp",
							Timeout:   "5s",
						},
					},
				}
			},
		},
		{
			name: "enabled upstream with empty allowlist",
			mutate: func(s *MCPGatewaySpec) {
				s.Upstreams = []MCPGatewayUpstreamSpec{
					{
						Name:    "tools",
						Enabled: true,
						Connection: MCPGatewayConnectionSpec{
							Transport: MCPTransportStreamableHTTP,
							URL:       "https://mcp.example.com/mcp",
							Timeout:   "5s",
						},
						Tools: MCPGatewayToolPolicySpec{
							Policy: MCPToolPolicyAllowlist,
						},
					},
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			spec := valid
			tt.mutate(&spec)

			if err := spec.Validate(); err == nil {
				t.Fatal("Validate() expected an error, got nil")
			}
		})
	}
}

func TestMCPGatewaySpecAcceptsEnabledHTTPUpstream(t *testing.T) {
	spec := MCPGatewaySpec{
		Server: MCPGatewayServerSpec{
			Name:          "test",
			ListenAddress: "127.0.0.1:8081",
			Transport:     MCPTransportStreamableHTTP,
			Endpoint:      "/mcp",
		},
		Discovery: MCPGatewayDiscoverySpec{
			RefreshInterval: "60s",
		},
		Security: MCPGatewaySecuritySpec{
			Authentication: MCPGatewayAuthenticationSpec{
				Enabled:  true,
				Mode:     "bearer",
				TokenEnv: "AGENYX_MCP_GATEWAY_TOKEN",
			},
			Authorization: MCPGatewayAuthorizationSpec{
				DefaultPolicy: "deny",
			},
		},
		Execution: MCPGatewayExecutionSpec{
			Timeout:            "30s",
			MaxConcurrentCalls: 100,
		},
		Limits: MCPGatewayLimitsSpec{
			MaxArgumentsBytes: 1 << 20,
			MaxResultBytes:    4 << 20,
		},
		Upstreams: []MCPGatewayUpstreamSpec{
			{
				Name:    "internal-tools",
				Enabled: true,
				Connection: MCPGatewayConnectionSpec{
					Transport: MCPTransportStreamableHTTP,
					URL:       "https://mcp.example.com/mcp",
					Timeout:   "5s",
				},
				Tools: MCPGatewayToolPolicySpec{
					Policy:  MCPToolPolicyAllowlist,
					Allowed: []string{"search_documents", "get_document"},
				},
			},
		},
	}

	if err := spec.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
}
