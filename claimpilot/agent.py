"""ClaimPilot: a LangGraph claims-processing agent over 20 synthetic policy docs.

One root span per claim, `prompt.version` on that span, and the eval funnel attached to
the same span — the three things Homeostat correlates on. The agent itself is a small
ReAct loop (`langchain.agents.create_agent`) with two tools over the lexical retriever in
retriever.py; LangChain/Azure OpenAI calls are auto-traced by OpenLIT (see telemetry.py).
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from opentelemetry import trace

import chaos
from telemetry import init_telemetry
from eval import evaluate_and_emit
from retriever import get_retriever

load_dotenv()

tracer = trace.get_tracer("claimpilot")
PROMPTS = Path(__file__).parent / "prompts"
# Azure deployment name (not a model family string) — endpoint/key/api-version come from
# AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / OPENAI_API_VERSION (see .env.example).
MODEL = os.environ["MODEL"]

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
    # gpt-5.6-sol is a reasoning-class deployment: only the default temperature (1) is
    # accepted, so we don't pass temperature at all rather than force a rejected value.
    model = AzureChatOpenAI(azure_deployment=MODEL, max_tokens=512)
    graph = create_agent(model, tools=[lookup_policy, list_exclusions], system_prompt=system_prompt)
    result = graph.invoke({"messages": [("user", claim["question"])]})
    messages = result["messages"]
    answer = messages[-1].content
    context = "\n\n".join(m.content for m in messages if isinstance(m, ToolMessage))
    return answer, context


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
        if "question" not in c:  # skip the __note annotation entry
            continue
        try:
            process_claim(c)
            print(f"{c['id']}: processed")
        except Exception as e:  # one bad claim (or a bad API key) shouldn't sink the batch
            print(f"{c['id']}: FAILED — {e}")
