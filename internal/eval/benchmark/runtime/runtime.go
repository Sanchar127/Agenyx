package runtime

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/sanchar127/agenyx/internal/eval/benchmark"
)

// AgentRunRequest represents an agent execution request.
type AgentRunRequest struct {
	Intent string `json:"intent"`
}

// AgentRunResponse represents an agent execution response.
type AgentRunResponse struct {
	ExecutionID string `json:"execution_id"`
	Status      string `json:"status"`
}

// ChatCompletionRequest represents an LLM chat completion request.
type ChatCompletionRequest struct {
	Model     string    `json:"model"`
	Messages  []Message `json:"messages"`
	Temperature float64  `json:"temperature,omitempty"`
	MaxTokens  int      `json:"max_tokens,omitempty"`
}

// Message represents a chat message.
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// ChatCompletionResponse represents an LLM chat completion response.
type ChatCompletionResponse struct {
	ID      string   `json:"id"`
	Object  string   `json:"object"`
	Model   string   `json:"model"`
	Choices []Choice `json:"choices"`
}

// Choice represents a chat completion choice.
type Choice struct {
	Index   int     `json:"index"`
	Message Message `json:"message"`
}

// GatewayBenchmarkRunner runs benchmarks against the Agenyx API Gateway.
type GatewayBenchmarkRunner struct {
	*benchmark.HTTPRunner
	gatewayURL string
}

// NewGatewayBenchmarkRunner creates a new gateway benchmark runner.
func NewGatewayBenchmarkRunner(store benchmark.Store, gatewayURL string, timeoutSeconds int) *GatewayBenchmarkRunner {
	return &GatewayBenchmarkRunner{
		HTTPRunner:  benchmark.NewHTTPRunner(store, timeoutSeconds),
		gatewayURL:  gatewayURL,
	}
}

// RunHealthBenchmark runs a health check benchmark against the gateway.
func (r *GatewayBenchmarkRunner) RunHealthBenchmark(ctx context.Context, config benchmark.BenchmarkConfig) (*benchmark.BenchmarkRun, error) {
	config.TargetURL = r.gatewayURL + "/health"
	config.Type = benchmark.BenchmarkTypeThroughput
	return r.HTTPRunner.Run(ctx, config)
}

// RunAgentRunBenchmark runs an agent run benchmark against the gateway.
func (r *GatewayBenchmarkRunner) RunAgentRunBenchmark(ctx context.Context, config benchmark.BenchmarkConfig, intent string) (*benchmark.BenchmarkRun, error) {
	payload, err := json.Marshal(AgentRunRequest{Intent: intent})
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	config.TargetURL = r.gatewayURL + "/v1/agent/run"
	config.Type = benchmark.BenchmarkTypeThroughput
	config.Payload = string(payload)
	config.ContentType = "application/json"

	return r.HTTPRunner.Run(ctx, config)
}

// InferenceBenchmarkRunner runs benchmarks against the Agenyx Inference Service.
type InferenceBenchmarkRunner struct {
	*benchmark.HTTPRunner
	inferenceURL string
}

// NewInferenceBenchmarkRunner creates a new inference benchmark runner.
func NewInferenceBenchmarkRunner(store benchmark.Store, inferenceURL string, timeoutSeconds int) *InferenceBenchmarkRunner {
	return &InferenceBenchmarkRunner{
		HTTPRunner:    benchmark.NewHTTPRunner(store, timeoutSeconds),
		inferenceURL:  inferenceURL,
	}
}

// RunChatCompletionBenchmark runs a chat completion benchmark against the inference service.
func (r *InferenceBenchmarkRunner) RunChatCompletionBenchmark(ctx context.Context, config benchmark.BenchmarkConfig, model string, prompt string) (*benchmark.BenchmarkRun, error) {
	request := ChatCompletionRequest{
		Model:         model,
		Messages:    []Message{{Role: "user", Content: prompt}},
		Temperature: 0.2,
		MaxTokens:   100,
	}
	payload, err := json.Marshal(request)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	config.TargetURL = r.inferenceURL + "/v1/chat/completions"
	config.Type = benchmark.BenchmarkTypeLatency
	config.Payload = string(payload)
	config.ContentType = "application/json"

	return r.HTTPRunner.Run(ctx, config)
}

// AgentBenchmarkRunner runs benchmarks against the Agenyx Agent Service.
type AgentBenchmarkRunner struct {
	*benchmark.HTTPRunner
	agentURL string
}

// NewAgentBenchmarkRunner creates a new agent benchmark runner.
func NewAgentBenchmarkRunner(store benchmark.Store, agentURL string, timeoutSeconds int) *AgentBenchmarkRunner {
	return &AgentBenchmarkRunner{
		HTTPRunner:  benchmark.NewHTTPRunner(store, timeoutSeconds),
		agentURL:    agentURL,
	}
}

// RunAgentIntentBenchmark runs an agent intent benchmark against the agent service.
func (r *AgentBenchmarkRunner) RunAgentIntentBenchmark(ctx context.Context, config benchmark.BenchmarkConfig, intent string) (*benchmark.BenchmarkRun, error) {
	payload, err := json.Marshal(AgentRunRequest{Intent: intent})
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	config.TargetURL = r.agentURL + "/v1/agent/run"
	config.Type = benchmark.BenchmarkTypeLatency
	config.Payload = string(payload)
	config.ContentType = "application/json"

	return r.HTTPRunner.Run(ctx, config)
}
