"""ClaimPilot: a LangGraph claims-processing agent over 20 synthetic policy docs.

One root span per claim, `prompt.version` on that span, and the eval funnel attached to
the same span — the three things Homeostat correlates on. The agent itself is a small
ReAct loop (`langchain.agents.create_agent`) with two tools over the lexical retriever in
retriever.py; LangChain/Azure OpenAI calls are auto-traced by OpenLIT (see telemetry.py).
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from opentelemetry import trace

import chaos
from telemetry import init_telemetry, shutdown
from eval import evaluate_and_emit, claims_processed
from retriever import get_retriever

log = logging.getLogger("claimpilot")

load_dotenv()

tracer = trace.get_tracer("claimpilot")
PROMPTS = Path(__file__).parent / "prompts"
# Azure deployment name (not a model family string). Named AZURE_OPENAI_DEPLOYMENT rather
# than MODEL: Windows env vars are case-insensitive and Dell laptops ship an OEM
# "Model=5440" that silently wins, because load_dotenv() never overrides process vars.
MODEL = os.environ["AZURE_OPENAI_DEPLOYMENT"]

_retriever = get_retriever()


def load_prompt(version: str) -> str:
    return (PROMPTS / f"{version}.txt").read_text(encoding="utf-8")


@tool
def lookup_policy(policy_id: str, query: str) -> str:
    """Retrieve the most relevant policy clauses for a policy id (HP-100 or AU-220) and a
    natural-language query. Returns the matched clause text, or a not-found message if
    nothing in the corpus is relevant enough — do not guess coverage when this happens."""
    if "lookup_policy" in chaos.DISABLED_TOOLS:
        return "ERROR: lookup_policy is temporarily disabled. Do not answer this claim."
    if chaos.FLAGS["broken_json_tool"]:
        # Reproducible failure class: the upstream policy service starts returning
        # malformed JSON. The agent sees tool errors and retries — tool-error and token
        # signals move (unlike the prompt regression). Heal = circuit_break("lookup_policy").
        raise ValueError(
            "policy-service response parse error: Expecting ',' delimiter: line 1 column 187"
            ' — raw: {"clauses": [{"id": "SEC-1", "text": "AU-220 covers physical dam'
        )
    results = _retriever.retrieve(query, policy_id=policy_id, k=3)
    if not results:
        return "No relevant policy clause found in the corpus."
    return "\n\n---\n\n".join(text for _, text, _ in results)


@tool
def list_exclusions(policy_id: str) -> str:
    """List all exclusion clauses for a policy id (HP-100 or AU-220), to check whether a
    peril is explicitly excluded rather than simply uncovered."""
    if "list_exclusions" in chaos.DISABLED_TOOLS:
        return "ERROR: list_exclusions is temporarily disabled. Do not answer this claim."
    docs = [text for name, text in _retriever.docs
            if name.upper().startswith(policy_id.upper()) and "exclusion" in name.lower()]
    if not docs:
        return "No exclusion clauses found for this policy."
    return "\n\n---\n\n".join(docs)


def run_agent(claim: dict, system_prompt: str) -> tuple[str, str]:
    """Run the ReAct agent over one claim. Returns (answer, retrieved_context) where
    retrieved_context is the concatenation of every tool result the agent actually saw —
    this is what the eval funnel checks the answer against, not the whole corpus."""
    # Azure's OpenAI-compatible v1 surface: deployment name goes in `model`, no dated
    # api-version needed. gpt-5.6-sol is a reasoning-class deployment — it rejects
    # non-default temperature and max_tokens, so neither is passed. The deployment comes
    # from the active RELEASE (chaos.active_model()): the v_overconfident release also
    # downgrades the model, which is what actually makes it hallucinate.
    # timeout is NOT optional: the default (none) blocked the claim loop forever on a
    # dead socket after a laptop suspend/VPN drop — a daemon thread stuck on an
    # infinite read looks "alive" while processing nothing (2026-07-24 incident).
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    model = ChatOpenAI(model=chaos.active_model(), api_key=os.environ["AZURE_OPENAI_API_KEY"],
                       base_url=f"{endpoint}/openai/v1/", timeout=120, max_retries=2)
    graph = create_agent(model, tools=[lookup_policy, list_exclusions], system_prompt=system_prompt)
    result = graph.invoke({"messages": [("user", claim["question"])]})
    messages = result["messages"]
    answer = messages[-1].content
    context = "\n\n".join(m.content for m in messages if isinstance(m, ToolMessage))
    return answer, context


def process_claim(claim: dict) -> dict:
    version = chaos.active_prompt_version()
    system_prompt = load_prompt(version)
    with tracer.start_as_current_span("claim.process") as root:
        root.set_attribute("claim.id", claim["id"])
        root.set_attribute("customer.tier", claim["tier"])
        root.set_attribute("prompt.version", version)  # <- lets the brain CORRELATE score↓ with version
        root.set_attribute("gen_ai.prompt.name", version)  # same identity, spec-registered name
        root.set_attribute("gen_ai.request.model", chaos.active_model())  # the release's model, on the root for grouping
        trace_id = format(root.get_span_context().trace_id, "032x")
        answer, context = run_agent(claim, system_prompt)   # LLM + tools auto-traced by OpenLIT
        return evaluate_and_emit(answer, context, claim, root, trace_id, version)


def run_claim_safely(claim: dict) -> dict | None:
    """process_claim + outcome accounting. A failed claim must show up in telemetry
    (claimpilot.claims.processed{outcome=error}), not just vanish from the SLI —
    otherwise an agent that crashes on every claim looks like one with no problems."""
    version = chaos.active_prompt_version()
    try:
        verdict = process_claim(claim)
        claims_processed.add(1, {"service.name": "claimpilot", "outcome": "ok",
                                 "prompt.version": version})
        return verdict
    except Exception:
        claims_processed.add(1, {"service.name": "claimpilot", "outcome": "error",
                                 "prompt.version": version})
        log.exception("claim %s failed", claim["id"])
        return None


if __name__ == "__main__":
    import json
    init_telemetry()
    claims = json.loads((Path(__file__).parent / "claims" / "claims.example.json").read_text())
    print(f"prompt={chaos.active_prompt_version()} model={MODEL} "
          f"otlp={os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')}")
    try:
        for c in claims:
            if "question" not in c:  # skip the __note annotation entry
                continue
            verdict = run_claim_safely(c)
            if verdict:
                print(f"{c['id']}: {verdict['label']} (score={verdict['score']})")
            else:  # one bad claim (or a bad API key) shouldn't sink the batch
                print(f"{c['id']}: FAILED — see log above")
    finally:
        shutdown()  # flush span/metric/log batches — a short batch run exits before they auto-export
