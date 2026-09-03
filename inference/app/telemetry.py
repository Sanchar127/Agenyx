from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_telemetry() -> None:
    """
    Configure OpenTelemetry tracing.

    Configuration is read from the standard OTEL_* environment
    variables provided by the OpenTelemetry SDK/exporter.
    """

    resource = Resource.create(
        {
            "service.name": "agenyx-inference",
            "service.namespace": "agenyx",
        }
    )

    tracer_provider = TracerProvider(
        resource=resource,
    )

    exporter = OTLPSpanExporter(
        insecure=True,
    )

    tracer_provider.add_span_processor(
        BatchSpanProcessor(exporter)
    )

    trace.set_tracer_provider(tracer_provider)


def instrument_app(app) -> None:
    """
    Instrument FastAPI and HTTPX.

    FastAPI creates incoming HTTP server spans.
    HTTPX creates outgoing HTTP client spans.
    """

    FastAPIInstrumentor.instrument_app(app)

    HTTPXClientInstrumentor().instrument()
