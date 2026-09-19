from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import Settings

def configure_telemetry(settings: Settings) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.namespace": settings.otel_service_namespace,
        }
    )

    tracer_provider = TracerProvider(
        resource=resource,
    )

    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )

    tracer_provider.add_span_processor(
        BatchSpanProcessor(exporter)
    )

    trace.set_tracer_provider(tracer_provider)

    return tracer_provider


def instrument_app(app) -> None:
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
