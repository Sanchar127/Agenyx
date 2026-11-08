package eval

import (
	"context"
	"fmt"
	"os"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	oteltrace "go.opentelemetry.io/otel/trace"
)

// TracerProvider wraps the OpenTelemetry tracer provider.
type TracerProvider struct {
	provider *sdktrace.TracerProvider
}

// NewTracerProvider creates a new OpenTelemetry tracer provider.
func NewTracerProvider(serviceName string) (*TracerProvider, error) {
	resourceAttrs := []attribute.KeyValue{
		semconv.ServiceName(serviceName),
		semconv.ServiceVersion("0.1.0"),
	}

	// Allow overriding resource attributes via environment
	if envAttrs := os.Getenv("EVAL_OTEL_RESOURCE_ATTRIBUTES"); envAttrs != "" {
		for _, pair := range splitEnvPairs(envAttrs) {
			if len(pair) == 2 {
				resourceAttrs = append(resourceAttrs, attribute.String(pair[0], pair[1]))
			}
		}
	}

	res := resource.NewWithAttributes(
		semconv.SchemaURL,
		resourceAttrs...,
	)

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.ParentBased(sdktrace.TraceIDRatioBased(1.0))),
	)

	otel.SetTracerProvider(tp)

	return &TracerProvider{provider: tp}, nil
}

// Shutdown shuts down the tracer provider.
func (tp *TracerProvider) Shutdown(ctx context.Context) error {
	return tp.provider.Shutdown(ctx)
}

// Tracer returns a tracer with the given name.
func (tp *TracerProvider) Tracer(name string) oteltrace.Tracer {
	return tp.provider.Tracer(name)
}

// splitEnvPairs splits a comma-separated key=value string into pairs.
func splitEnvPairs(s string) [][]string {
	pairs := make([][]string, 0)
	for _, pair := range splitEnvCommas(s) {
		kv := splitEnvKeyValue(pair)
		if len(kv) == 2 {
			pairs = append(pairs, kv)
		}
	}
	return pairs
}

func splitEnvCommas(s string) []string {
	var result []string
	current := ""
	for _, c := range s {
		if c == ',' {
			result = append(result, current)
			current = ""
		} else {
			current += string(c)
		}
	}
	if current != "" {
		result = append(result, current)
	}
	return result
}

func splitEnvKeyValue(s string) []string {
	for i, c := range s {
		if c == '=' {
			return []string{s[:i], s[i+1:]}
		}
	}
	return []string{s}
}

// StartSpan starts a new span with the given name.
func StartSpan(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, oteltrace.Span) {
	tracer := otel.Tracer("evaluation")
	ctx, span := tracer.Start(ctx, name, oteltrace.WithAttributes(attrs...))
	return ctx, span
}

// EndSpan ends a span with the given status and optional error.
func EndSpan(ctx context.Context, span oteltrace.Span, err error) {
	if span == nil {
		return
	}
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
	} else {
		span.SetStatus(codes.Ok, "")
	}
	span.End()
}

// RecordEvaluationStart records the start of an evaluation.
func RecordEvaluationStart(ctx context.Context, evalID string, evalType string) (context.Context, oteltrace.Span) {
	return StartSpan(ctx, "evaluation.run",
		attribute.String("evaluation.id", evalID),
		attribute.String("evaluation.type", string(evalType)),
	)
}

// RecordEvaluationEnd ends an evaluation span with the result.
func RecordEvaluationEnd(ctx context.Context, span oteltrace.Span, successRate float64, chunksRetrieved int, contextChars int, err error) {
	if span == nil {
		return
	}
	span.SetAttributes(
		attribute.Float64("evaluation.success_rate", successRate),
		attribute.Int("evaluation.chunks_retrieved", chunksRetrieved),
		attribute.Int("evaluation.context_chars", contextChars),
	)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
	} else {
		span.SetStatus(codes.Ok, "")
	}
	span.End()
}

// MustNewTracerProvider creates a new TracerProvider or panics on error.
func MustNewTracerProvider(serviceName string) *TracerProvider {
	tp, err := NewTracerProvider(serviceName)
	if err != nil {
		panic(fmt.Sprintf("failed to create telemetry provider: %v", err))
	}
	return tp
}
