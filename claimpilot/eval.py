"""The eval spine (the moat) + the production-cheap funnel.

Tier 0 (deterministic, $0) and Tier 1 (cheap/local proxy) gate the expensive
Tier 2 LLM judge. Only flagged + a small calibration sample reach Tier 2.
The verdict is written as ATTRIBUTES on the existing root span (no extra span
row) plus a bounded-cardinality metric. Reason is stored only on flagged spans.
"""
import logging
from opentelemetry import trace, metrics

tracer = trace.get_tracer("claimpilot")
meter = metrics.get_meter("claimpilot")
faithfulness = meter.create_histogram(
    "gen_ai.evaluation.score", description="LLM-judge faithfulness 0..1"
)
log = logging.getLogger("claimpilot")

CALIBRATION_RATE = 0.02  # sample rate for keeping the cheap tiers honest


# ---- Tier 0: deterministic, runs on 100%, no LLM ----
def tier0(answer: str, context: str) -> bool:
    """True == passes cheap checks. Extend: cites a chunk? abstained when context empty? format ok?"""
    if not context.strip() and answer.strip():
        return False  # answered with no supporting context -> suspicious
    return True


# ---- Tier 1: cheap ML proxy, runs on 100% (embedding cosine / local NLI) ----
def tier1_proxy(answer: str, context: str) -> float:
    """Return a cheap faithfulness proxy in 0..1. Replace with embedding cosine or a local NLI model."""
    # TODO: embedding cosine(answer, context) or a small local NLI entailment score.
    return 1.0


# ---- Tier 2: the authoritative LLM judge (expensive) ----
def judge(answer: str, context: str) -> dict:
    """claude-haiku-4-5, structured output {score: 0..1, reason: str}, max_tokens ~= 256.
    Prompt: 'Is ANSWER fully supported by CONTEXT? Score 0..1 + one-line reason. JSON only.'"""
    # TODO: call the Anthropic API with output_config.format (structured output) and max_tokens=256.
    raise NotImplementedError


def _sampled(claim: dict, rate: float) -> bool:
    # Deterministic sampling by claim id (no Math.random needed).
    return (hash(claim["id"]) % 100) < int(rate * 100)


def evaluate_and_emit(answer: str, context: str, claim: dict, root, trace_id: str,
                      prompt_version: str) -> dict | None:
    """Run the funnel; on escalation attach the verdict to `root` and emit the metric.
    Returns the verdict dict, or None if it stayed in the cheap tiers."""
    t0_ok = tier0(answer, context)
    proxy = tier1_proxy(answer, context)
    escalate = (not t0_ok) or (proxy < 0.6) or _sampled(claim, CALIBRATION_RATE)

    if not escalate:
        # still chart a cheap proxy on 100% of traffic
        faithfulness.record(proxy, {"service.name": "claimpilot", "eval.name": "faithfulness_proxy",
                                    "customer.tier": claim["tier"]})
        return None

    v = judge(answer, context)  # auto-traced by OpenLIT
    root.set_attribute("gen_ai.evaluation.name", "faithfulness")
    root.set_attribute("gen_ai.evaluation.score", v["score"])
    root.set_attribute("gen_ai.evaluation.label",
                       "supported" if v["score"] >= 0.5 else "unsupported")
    if v["score"] < 0.5:
        root.set_attribute("gen_ai.evaluation.reason", v["reason"])  # reason on flagged only (disk)
        # WARN log carrying trace_id -> the 5th signal (logs) correlated to the failing span
        log.warning("unsupported answer", extra={"trace_id": trace_id, "claim_id": claim["id"],
                                                 "prompt_version": prompt_version})
    # BOUNDED labels only — never claim.id / trace_id / reason / score-as-label on a metric
    faithfulness.record(v["score"], {"service.name": "claimpilot", "eval.name": "faithfulness",
                                     "customer.tier": claim["tier"]})
    return v
