"""OTLP telemetry init for ClaimPilot — traces + metrics + logs, one endpoint.

Owns the OTel SDK providers explicitly, then lets openlit.init() detect and reuse
them, so OpenLIT's auto-instrumented gen_ai.* spans and our custom spans/metrics/
logs all export to the same place. Logs matter: eval.py emits a WARN on every
unsupported answer, and exporting it via OTLP (with the active span's trace_id
attached automatically) is what makes the SigNoz log->failing-span pivot work.

Endpoint precedence (OTEL_EXPORTER_OTLP_ENDPOINT):
  - http://localhost:4318        local collector, agent on the host (default)
  - http://signoz-ingester:4318  dockerized (set by docker-compose.apps.yaml)
  - https://<host>/otlp          a remote SigNoz ingester, e.g. the dev VM

Short-lived batch runs MUST call shutdown() before exit — BatchSpanProcessor /
PeriodicExportingMetricReader flush on shutdown, not on process death.
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

# Internal https endpoints (e.g. signoz.apteancloud.dev) present a cert chain the
# OS trusts but Python's certifi bundle does not. truststore points Python's SSL
# verification at the OS trust store — verification still happens, same anchors
# the browser uses. Must be injected before requests/urllib3 bind their
# SSLContext; both are pulled in transitively by the exporters and openlit below.
import truststore

truststore.inject_into_ssl()

import openlit
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = "claimpilot"

_providers: list = []


def init_telemetry() -> None:
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    base = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").rstrip("/")
    # Both environment spellings: current semconv says deployment.environment.name, but
    # SigNoz's environment filter still keys on the older deployment.environment.
    resource = Resource.create(
        {"service.name": SERVICE_NAME,
         "deployment.environment": "hackathon",
         "deployment.environment.name": "hackathon"}
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"))
        ],
    )
    metrics.set_meter_provider(meter_provider)

    # Logs: the WARN "unsupported answer" must land in SigNoz carrying the failing
    # span's trace_id. LoggingHandler attaches the active span context automatically.
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{base}/v1/logs"))
    )
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))
    # Our own loggers must pass INFO (the gen_ai.evaluation.result events) while the
    # root stays at WARNING so third-party libraries (httpx et al.) don't flood SigNoz.
    logging.getLogger("claimpilot").setLevel(logging.INFO)
    # Failures must ALSO land locally (stderr -> the service's err log). During the
    # 2026-07-24 incident everything went only to the OTLP pipeline — which was down
    # with the same network that caused the failures, leaving zero local evidence.
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("claimpilot").addHandler(console)

    openlit.init(
        application_name=SERVICE_NAME,   # -> service.name in SigNoz
        environment="hackathon",
        otlp_endpoint=base,
        capture_message_content=True,    # prompts + completions land ON the span
    )

    _providers.extend([tracer_provider, meter_provider, logger_provider])


def shutdown() -> None:
    """Flush and shut down every provider. Batch runs must call this before exit."""
    for provider in _providers:
        provider.shutdown()
