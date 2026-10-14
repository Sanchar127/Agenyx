package recipe

import (
	"errors"
	"fmt"
	"net"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const MCPGatewayRecipeKind = "MCPGatewayRecipe"

const (
	MCPTransportStreamableHTTP = "streamable-http"
	MCPTransportStdio          = "stdio"
	MCPToolPolicyAllowlist     = "allowlist"
	MCPToolPolicyDenylist      = "denylist"
)

// MCPGatewaySpec defines the configuration for the MCP Gateway.
type MCPGatewaySpec struct {
	Server        MCPGatewayServerSpec        `yaml:"server"`
	Upstreams     []MCPGatewayUpstreamSpec    `yaml:"upstreams"`
	Discovery     MCPGatewayDiscoverySpec     `yaml:"discovery"`
	Security      MCPGatewaySecuritySpec      `yaml:"security"`
	Execution     MCPGatewayExecutionSpec     `yaml:"execution"`
	Limits        MCPGatewayLimitsSpec        `yaml:"limits"`
	Observability MCPGatewayObservabilitySpec `yaml:"observability"`
}

type MCPGatewayServerSpec struct {
	Name          string `yaml:"name"`
	ListenAddress string `yaml:"listenAddress"`
	Transport     string `yaml:"transport"`
	Endpoint      string `yaml:"endpoint"`
}

type MCPGatewayUpstreamSpec struct {
	Name       string                   `yaml:"name"`
	Enabled    bool                     `yaml:"enabled"`
	Connection MCPGatewayConnectionSpec `yaml:"connection"`
	Tools      MCPGatewayToolPolicySpec `yaml:"tools"`
}

type MCPGatewayConnectionSpec struct {
	Transport string            `yaml:"transport"`
	URL       string            `yaml:"url,omitempty"`
	Command   string            `yaml:"command,omitempty"`
	Args      []string          `yaml:"args,omitempty"`
	Env       map[string]string `yaml:"env,omitempty"`
	Timeout   string            `yaml:"timeout"`
}

type MCPGatewayToolPolicySpec struct {
	Policy  string   `yaml:"policy"`
	Allowed []string `yaml:"allowed,omitempty"`
	Denied  []string `yaml:"denied,omitempty"`
}

type MCPGatewayDiscoverySpec struct {
	RefreshInterval string `yaml:"refreshInterval"`
	CacheTools      bool   `yaml:"cacheTools"`
}

type MCPGatewaySecuritySpec struct {
	Authentication MCPGatewayAuthenticationSpec `yaml:"authentication"`
	Authorization  MCPGatewayAuthorizationSpec  `yaml:"authorization"`
}

type MCPGatewayAuthenticationSpec struct {
	Enabled  bool   `yaml:"enabled"`
	Mode     string `yaml:"mode"`
	TokenEnv string `yaml:"tokenEnv"`
}

type MCPGatewayAuthorizationSpec struct {
	DefaultPolicy string `yaml:"defaultPolicy"`
}

type MCPGatewayExecutionSpec struct {
	Timeout            string `yaml:"timeout"`
	MaxConcurrentCalls int    `yaml:"maxConcurrentCalls"`
}

type MCPGatewayLimitsSpec struct {
	MaxArgumentsBytes int64 `yaml:"maxArgumentsBytes"`
	MaxResultBytes    int64 `yaml:"maxResultBytes"`
}

type MCPGatewayObservabilitySpec struct {
	MetricsEnabled bool `yaml:"metricsEnabled"`
	TracingEnabled bool `yaml:"tracingEnabled"`
}

// Validate rejects invalid or unsafe MCP Gateway configuration.
func (s MCPGatewaySpec) Validate() error {
	if strings.TrimSpace(s.Server.Name) == "" {
		return errors.New("server.name must not be empty")
	}

	if strings.TrimSpace(s.Server.ListenAddress) == "" {
		return errors.New("server.listenAddress must not be empty")
	}

	host, portText, err := net.SplitHostPort(s.Server.ListenAddress)
	if err != nil {
		return fmt.Errorf("server.listenAddress is invalid: %w", err)
	}
	_ = host

	port, err := strconv.Atoi(portText)
	if err != nil || port < 1 || port > 65535 {
		return errors.New("server.listenAddress must contain a valid TCP port")
	}

	if s.Server.Transport != MCPTransportStreamableHTTP {
		return fmt.Errorf(
			"server.transport must be %q",
			MCPTransportStreamableHTTP,
		)
	}

	if !strings.HasPrefix(s.Server.Endpoint, "/") ||
		strings.ContainsAny(s.Server.Endpoint, "?#") {
		return errors.New(
			"server.endpoint must be an absolute path without a query or fragment",
		)
	}

	if err := validateDuration(
		"discovery.refreshInterval",
		s.Discovery.RefreshInterval,
		time.Second,
		24*time.Hour,
	); err != nil {
		return err
	}

	if s.Security.Authentication.Enabled {
		if s.Security.Authentication.Mode != "bearer" {
			return errors.New(
				"security.authentication.mode must be bearer when authentication is enabled",
			)
		}

		if strings.TrimSpace(s.Security.Authentication.TokenEnv) == "" {
			return errors.New(
				"security.authentication.tokenEnv must not be empty when authentication is enabled",
			)
		}
	}

	if s.Security.Authorization.DefaultPolicy != "deny" {
		return errors.New(
			"security.authorization.defaultPolicy must be deny",
		)
	}

	if err := validateDuration(
		"execution.timeout",
		s.Execution.Timeout,
		time.Millisecond,
		10*time.Minute,
	); err != nil {
		return err
	}

	if s.Execution.MaxConcurrentCalls < 1 ||
		s.Execution.MaxConcurrentCalls > 10000 {
		return errors.New(
			"execution.maxConcurrentCalls must be between 1 and 10000",
		)
	}

	if s.Limits.MaxArgumentsBytes < 1 ||
		s.Limits.MaxArgumentsBytes > 16<<20 {
		return errors.New(
			"limits.maxArgumentsBytes must be between 1 byte and 16 MiB",
		)
	}

	if s.Limits.MaxResultBytes < 1 ||
		s.Limits.MaxResultBytes > 64<<20 {
		return errors.New(
			"limits.maxResultBytes must be between 1 byte and 64 MiB",
		)
	}

	names := make(map[string]struct{}, len(s.Upstreams))

	for i, upstream := range s.Upstreams {
		name := strings.TrimSpace(upstream.Name)
		if name == "" {
			return fmt.Errorf("upstreams[%d].name must not be empty", i)
		}

		if _, exists := names[name]; exists {
			return fmt.Errorf("duplicate upstream name %q", name)
		}
		names[name] = struct{}{}

		// Disabled upstreams are allowed in configuration but are not
		// expected to be connected by the runtime.
		if !upstream.Enabled {
			continue
		}

		if err := validateUpstream(i, upstream); err != nil {
			return err
		}
	}

	return nil
}

func validateUpstream(index int, upstream MCPGatewayUpstreamSpec) error {
	prefix := fmt.Sprintf("upstreams[%d]", index)

	switch upstream.Connection.Transport {
	case MCPTransportStreamableHTTP:
		rawURL := strings.TrimSpace(upstream.Connection.URL)
		if rawURL == "" {
			return fmt.Errorf("%s.connection.url is required", prefix)
		}

		parsed, err := url.ParseRequestURI(rawURL)
		if err != nil ||
			(parsed.Scheme != "http" && parsed.Scheme != "https") ||
			parsed.Hostname() == "" ||
			parsed.User != nil ||
			parsed.Fragment != "" {
			return fmt.Errorf(
				"%s.connection.url must be a valid HTTP(S) URL without embedded credentials or a fragment",
				prefix,
			)
		}

	case MCPTransportStdio:
		if strings.TrimSpace(upstream.Connection.Command) == "" {
			return fmt.Errorf("%s.connection.command is required for stdio", prefix)
		}

		if upstream.Connection.URL != "" {
			return fmt.Errorf("%s.connection.url must be empty for stdio", prefix)
		}

	default:
		return fmt.Errorf(
			"%s.connection.transport must be %q or %q",
			prefix,
			MCPTransportStreamableHTTP,
			MCPTransportStdio,
		)
	}

	if err := validateDuration(
		prefix+".connection.timeout",
		upstream.Connection.Timeout,
		time.Millisecond,
		10*time.Minute,
	); err != nil {
		return err
	}

	switch upstream.Tools.Policy {
	case MCPToolPolicyAllowlist:
		if len(upstream.Tools.Allowed) == 0 {
			return fmt.Errorf(
				"%s.tools.allowed must contain at least one tool for an allowlist policy",
				prefix,
			)
		}

		if err := validateUniqueToolNames(prefix+".tools.allowed", upstream.Tools.Allowed); err != nil {
			return err
		}

	case MCPToolPolicyDenylist:
		if err := validateUniqueToolNames(prefix+".tools.denied", upstream.Tools.Denied); err != nil {
			return err
		}

	default:
		return fmt.Errorf(
			"%s.tools.policy must be %q or %q",
			prefix,
			MCPToolPolicyAllowlist,
			MCPToolPolicyDenylist,
		)
	}

	return nil
}

func validateUniqueToolNames(field string, names []string) error {
	seen := make(map[string]struct{}, len(names))

	for _, name := range names {
		name = strings.TrimSpace(name)
		if name == "" {
			return fmt.Errorf("%s must not contain empty tool names", field)
		}

		if _, exists := seen[name]; exists {
			return fmt.Errorf("%s contains duplicate tool name %q", field, name)
		}

		seen[name] = struct{}{}
	}

	return nil
}

func validateDuration(
	field string,
	raw string,
	minimum time.Duration,
	maximum time.Duration,
) error {
	duration, err := time.ParseDuration(raw)
	if err != nil {
		return fmt.Errorf("%s must be a valid duration: %w", field, err)
	}

	if duration < minimum || duration > maximum {
		return fmt.Errorf(
			"%s must be between %s and %s",
			field,
			minimum,
			maximum,
		)
	}

	return nil
}

// LoadMCPGatewaySpec loads and validates an MCP Gateway recipe.
func LoadMCPGatewaySpec(path string) (MCPGatewaySpec, error) {
	doc, err := LoadFile(path)
	if err != nil {
		return MCPGatewaySpec{}, err
	}

	if doc.Kind != MCPGatewayRecipeKind {
		return MCPGatewaySpec{}, fmt.Errorf(
			"unexpected recipe kind %q; expected %q",
			doc.Kind,
			MCPGatewayRecipeKind,
		)
	}

	var spec MCPGatewaySpec
	if err := doc.DecodeSpec(&spec); err != nil {
		return MCPGatewaySpec{}, err
	}

	if err := spec.Validate(); err != nil {
		return MCPGatewaySpec{}, fmt.Errorf(
			"validate MCP gateway recipe: %w",
			err,
		)
	}

	return spec, nil
}
