"""OTLP telemetry init. OpenLIT auto-instruments LangChain/LangGraph + the LLM SDK
and exports gen_ai.* spans to SigNoz (via the OTel collector)."""
import os
import openlit


def init_telemetry() -> None:
    # Export to the collector, not straight to SigNoz.
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    openlit.init(
        application_name="claimpilot",   # -> service.name in SigNoz
        environment="hackathon",
        capture_message_content=True,     # prompts + completions land ON the span
    )
