"""The brain: SigNoz alert webhook -> bounded MCP investigation -> evidence-linked
Slack report -> human approval -> reversible remediation -> verified recovery.

Restraint by construction: the read surface is signoz_client (bounded queries only),
the write surface is remediate (two allowlisted reversible actions), and nothing is
applied without a human click — except explicitly safe no-op explanations.

The loop observes ITSELF into the same SigNoz: every stage is a span under service
homeostat-brain tagged homeostat.action, so the healer shows up next to the damage
it fixed.

Run:  uvicorn main:app --port 8090
Test: POST /webhook with a SigNoz alert payload (see /simulate for a canned one).
"""
import logging
import os
import threading
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "claimpilot" / ".env")

import truststore

truststore.inject_into_ssl()

from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import investigate as investigator
import remediate
import slack
import verify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("homeostat.brain")

OTLP = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://signoz.apteancloud.dev/otlp").rstrip("/")
_provider = TracerProvider(resource=Resource.create({"service.name": "homeostat-brain",
                                                     "deployment.environment": "hackathon"}))
_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTLP}/v1/traces")))
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer("homeostat-brain")

APPROVAL_TIMEOUT_S = int(os.getenv("BRAIN_APPROVAL_TIMEOUT_S", "900"))
# Unattended-drill mode: applies the proposed action WITHOUT a human click. OFF by
# default — the product's restraint story requires human approval; this exists only so
# scheduled/overnight drills can exercise the full heal+verify path. Every use is
# labeled as auto-approved in Slack and in the trace.
AUTO_APPROVE = os.getenv("BRAIN_AUTO_APPROVE", "0") == "1"
_in_flight: set[str] = set()
_lock = threading.Lock()

app = FastAPI(title="homeostat-brain")


def choose_action(report: dict) -> dict:
    """Map findings -> a reversible, allowlisted action. No freeform commands, ever."""
    if report.get("offending_version") and report.get("prev_version"):
        return {"name": "pin_prompt_version",
                "params": {"version": report["prev_version"]}, "risk": "risky"}
    return {"name": "explain_only", "params": {}, "risk": "safe"}


def apply(action: dict) -> None:
    if action["name"] == "pin_prompt_version":
        remediate.pin_prompt_version(action["params"]["version"])
    elif action["name"] == "circuit_break":
        remediate.circuit_break(action["params"]["tool"])
    # explain_only: nothing to do — the report itself is the output


def handle_incident(alert: dict) -> None:
    incident_id = uuid.uuid4().hex[:8]
    alert_name = alert.get("labels", {}).get("alertname", "unknown alert")
    with tracer.start_as_current_span("brain.incident") as root:
        root.set_attribute("homeostat.action", "incident")
        root.set_attribute("incident.id", incident_id)
        root.set_attribute("alert.name", alert_name)
        log.info("[%s] investigating '%s'", incident_id, alert_name)

        with tracer.start_as_current_span("brain.investigate"):
            report = investigator.investigate(alert)
        action = choose_action(report)
        root.set_attribute("homeostat.proposed_action", action["name"])
        log.info("[%s] %s -> proposing %s", incident_id, report["summary"], action["name"])

        thread_ts = slack.post_report(incident_id, report, action)

        if action["risk"] == "safe":
            return  # nothing to apply; the evidence report was the whole job

        with tracer.start_as_current_span("brain.await_approval") as span:
            if AUTO_APPROVE:
                decision, user = "approved", "AUTO-APPROVE (unattended drill mode)"
                slack.post_update("⚙️ unattended drill mode: proposed action auto-approved.",
                                  thread_ts)
            else:
                decision, user = slack.wait_approval(incident_id, APPROVAL_TIMEOUT_S)
            span.set_attribute("approval.decision", decision)
            span.set_attribute("approval.user", user or "")
        log.info("[%s] decision: %s (by %s)", incident_id, decision, user)

        if decision != "approved":
            slack.post_update(f"No action applied ({decision}). The alert will keep firing "
                              f"until a human intervenes or the SLI recovers on its own.",
                              thread_ts)
            return

        with tracer.start_as_current_span("brain.remediate") as span:
            span.set_attribute("homeostat.action", action["name"])
            span.set_attribute("prompt.version", action["params"].get("version", ""))
            apply(action)
        slack.post_update(f"🔧 applied `{action['name']}({action['params']})` — verifying the SLI "
                          f"recovers (target ≥ {verify.RECOVERY_TARGET}, up to 15 min)…", thread_ts)

        with tracer.start_as_current_span("brain.verify") as span:
            recovered = verify.verify_recovery(report, thread_ts)
            span.set_attribute("verify.recovered", recovered)


@app.post("/webhook")
async def webhook(req: Request):
    payload = await req.json()
    for alert in payload.get("alerts", []):
        if alert.get("status") != "firing":
            continue
        key = alert.get("fingerprint") or alert.get("labels", {}).get("alertname", "?")
        with _lock:
            if key in _in_flight:
                log.info("alert %s already in flight — skipping duplicate webhook", key)
                continue
            _in_flight.add(key)

        def run(a=alert, k=key):
            try:
                handle_incident(a)
            except Exception:
                log.exception("incident handling failed")
                slack.post_update("🚨 homeostat brain crashed mid-incident — see brain logs.")
            finally:
                with _lock:
                    _in_flight.discard(k)

        threading.Thread(target=run, daemon=True, name=f"incident-{key[:12]}").start()
    return {"ok": True}


@app.post("/simulate")
async def simulate():
    """Local test hook: inject a canned firing alert (what SigNoz would POST)."""
    fake = {"alerts": [{"status": "firing",
                        "fingerprint": f"simulated-{int(time.time())}",
                        "labels": {"alertname": "Faithfulness SLO fast burn — claimpilot",
                                   "severity": "critical", "service": "claimpilot",
                                   "threshold.name": "critical"},
                        "annotations": {"summary": "simulated fire for local testing"}}]}
    return await webhook(_FakeRequest(fake))


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@app.get("/health")
def health():
    return {"ok": True, "in_flight": len(_in_flight)}


@app.on_event("startup")
def _startup():
    slack.start_socket_listener()

# run: uvicorn main:app --port 8090
