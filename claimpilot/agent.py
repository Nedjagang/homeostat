"""ClaimPilot: a LangGraph claims-processing agent over ~20 synthetic policy docs.

Schematic wiring — fill in the LangGraph graph + RAG retriever. The key parts for
Homeostat are: (1) one root span per claim, (2) prompt.version on the span,
(3) the eval funnel attached to the same span.
"""
from pathlib import Path
from opentelemetry import trace

import chaos
from telemetry import init_telemetry
from eval import evaluate_and_emit

tracer = trace.get_tracer("claimpilot")
PROMPTS = Path(__file__).parent / "prompts"


def load_prompt(version: str) -> str:
    return (PROMPTS / f"{version}.txt").read_text(encoding="utf-8")


def run_agent(claim: dict, system_prompt: str) -> tuple[str, str]:
    """TODO: LangGraph agent with tools (lookup_policy, check_coverage, calc_payout, decide)
    + RAG over policies/. Returns (answer, retrieved_context)."""
    raise NotImplementedError


def process_claim(claim: dict) -> None:
    version = chaos.active_prompt_version()
    system_prompt = load_prompt(version)
    with tracer.start_as_current_span("claim.process") as root:
        root.set_attribute("claim.id", claim["id"])
        root.set_attribute("customer.tier", claim["tier"])
        root.set_attribute("prompt.version", version)  # <- lets the brain CORRELATE score↓ with version
        trace_id = format(root.get_span_context().trace_id, "032x")
        answer, context = run_agent(claim, system_prompt)   # LLM + tools auto-traced by OpenLIT
        evaluate_and_emit(answer, context, claim, root, trace_id, version)


if __name__ == "__main__":
    import json
    init_telemetry()
    claims = json.loads((Path(__file__).parent / "claims" / "claims.example.json").read_text())
    for c in claims:
        process_claim(c)
