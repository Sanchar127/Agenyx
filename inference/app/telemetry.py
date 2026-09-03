from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


OTEL_ENDPOINT = (
    "http://agenyx-otel-collector.monitoring.svc.cluster.local:4317"
)


def configure_telemetry() -> None:
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
        endpoint=OTEL_ENDPOINT,
        insecure=True,
    )

    tracer_provider.add_span_processor(
        BatchSpanProcessor(exporter)
    )

    trace.set_tracer_provider(tracer_provider)


def instrument_app(app) -> None:
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
