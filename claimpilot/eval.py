"""The eval spine (the moat) + the production-cheap funnel.

Day 1 (today): Tier 0 only, running on 100% of claims, $0 cost — deterministic
grounding check, written as ATTRIBUTES on the existing root span (no extra span
row) plus the bounded gen_ai.evaluation.score metric. This is what proves
telemetry end-to-end: agent -> collector -> SigNoz, with a real quality signal
on every trace.

Tier 1 (cheap/local proxy) and Tier 2 (LLM judge) are the escalation funnel that
gates the expensive judge behind Tier 0 + a small calibration sample — that
wiring lands later in the build (see TODO.md, Agent A / GATE 2, 2A). The
functions are stubbed below so the shape is locked, but evaluate_and_emit does
not call them yet.
"""
import logging
from opentelemetry import trace, metrics

tracer = trace.get_tracer("claimpilot")
meter = metrics.get_meter("claimpilot")
faithfulness = meter.create_histogram(
    "gen_ai.evaluation.score", description="Bounded 0..1 quality signal (tier0_grounding today, judge later)"
)
log = logging.getLogger("claimpilot")

CALIBRATION_RATE = 0.02  # sample rate for keeping the cheap tiers honest (Tier 2, not wired yet)

# The exact abstention string required by prompts/v1_grounded.txt. Tier 0 must not
# flag a correct abstention just because it happened to come with empty context —
# only an answer with NO supporting context AND NO abstention is suspicious.
ABSTENTION_PHRASE = "i don't have enough information in the policy to determine this"


# ---- Tier 0: deterministic, runs on 100%, no LLM ----
def tier0(answer: str, context: str) -> bool:
    """True == passes cheap checks: grounded in retrieved context, or correctly abstained
    when no context was found. False == answered confidently with nothing to back it up —
    exactly the overconfident-prompt failure mode this whole project targets."""
    if context.strip():
        return True
    return ABSTENTION_PHRASE in answer.strip().lower()


# ---- Tier 1: cheap ML proxy, runs on 100% (embedding cosine / local NLI) ----
def tier1_proxy(answer: str, context: str) -> float:
    """Return a cheap faithfulness proxy in 0..1. Replace with embedding cosine or a local NLI model."""
    # TODO: embedding cosine(answer, context) or a small local NLI entailment score.
    return 1.0


# ---- Tier 2: the authoritative LLM judge (expensive) ----
def judge(answer: str, context: str) -> dict:
    """Azure OpenAI (the MODEL deployment configured in .env), structured output
    {score: 0..1, reason: str}, max_tokens ~= 256.
    Prompt: 'Is ANSWER fully supported by CONTEXT? Score 0..1 + one-line reason. JSON only.'"""
    # TODO: call AzureChatOpenAI with structured output (with_structured_output) and max_tokens=256.
    raise NotImplementedError


def _sampled(claim: dict, rate: float) -> bool:
    # Deterministic sampling by claim id (no Math.random needed).
    return (hash(claim["id"]) % 100) < int(rate * 100)


def evaluate_and_emit(answer: str, context: str, claim: dict, root, trace_id: str,
                      prompt_version: str) -> dict:
    """Day 1: Tier 0 only, on every claim. Attaches the verdict to `root` (attributes) and
    emits the bounded gen_ai.evaluation.score metric. Tier 1/2 escalation (judge, calibration
    sampling) is not wired in yet — see the module docstring."""
    t0_ok = tier0(answer, context)
    score = 1.0 if t0_ok else 0.0
    label = "grounded" if t0_ok else "unsupported"

    root.set_attribute("gen_ai.evaluation.name", "tier0_grounding")
    root.set_attribute("gen_ai.evaluation.score", score)
    root.set_attribute("gen_ai.evaluation.label", label)
    if not t0_ok:
        root.set_attribute("gen_ai.evaluation.reason", "answered with no supporting context and no abstention")
        # WARN log carrying trace_id -> the 5th signal (logs) correlated to the failing span
        log.warning("unsupported answer", extra={"trace_id": trace_id, "claim_id": claim["id"],
                                                 "prompt_version": prompt_version})
    # BOUNDED labels only — never claim.id / trace_id / reason / score-as-label on a metric
    faithfulness.record(score, {"service.name": "claimpilot", "eval.name": "tier0_grounding",
                                "customer.tier": claim["tier"]})
    return {"score": score, "label": label}
