"""OpenTelemetry setup — opt-in via OTLP_ENDPOINT env var."""

import logging
import os

logger = logging.getLogger(__name__)


def setup_telemetry(app, engine=None):
    """Instrument FastAPI, SQLAlchemy, Redis, and httpx with OpenTelemetry.

    No-op if OTLP_ENDPOINT is not set.
    """
    otlp_endpoint = os.getenv("OTLP_ENDPOINT")
    if not otlp_endpoint:
        logger.info("Telemetry disabled — OTLP_ENDPOINT not set")
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "workflow-backend"),
            "deployment.environment": os.getenv("DEPLOY_TARGET", "unknown"),
        }
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    RedisInstrumentor().instrument()

    if engine is not None:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        except Exception as e:
            logger.warning("SQLAlchemy instrumentation failed: %s", e)

    logger.info("Telemetry enabled → %s", otlp_endpoint)
