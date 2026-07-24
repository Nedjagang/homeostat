"""The eval spine (the moat) + the production-cheap funnel.

The funnel (all three tiers live):
  Tier 0  deterministic, 100% of claims, $0 — "answered with NO retrieved context and
          no abstention" is provably unsupported, no LLM needed.
  Tier 1  lexical overlap proxy, 100% of Tier-0 passes, $0 — routes only SUSPICIOUS
          answers (low answer↔context overlap) to the judge.
  Tier 2  the LLM judge — authoritative 0..1 verdict, runs on Tier-1-flagged answers
          plus a ~2% calibration sample that keeps the cheap tiers honest.
EVAL_JUDGE_MODE=all disables the gating (judge on every Tier-0 pass) for demos and
calibration batches. The routing decision lands on the span as eval.route, so the
judge-share economics are visible per-claim in SigNoz.

The verdict is emitted three ways:
  1. ATTRIBUTES on the existing root span, spec-exact per the OTel GenAI semantic
     conventions (gen_ai.evaluation.name / .score.value / .score.label /
     .explanation) — the drill-down surface.
  2. A `gen_ai.evaluation.result` LOG EVENT parented to the same trace — the shape
     the conventions actually standardize (semantic-conventions-genai repo).
  3. The bounded gen_ai.evaluation.score METRIC — dashboards + the SLO alert. The
     conventions define NO metric for eval scores yet, so this name is ours; the
     labels are deliberately low-cardinality.
A WARN log carrying the trace_id additionally fires on every unsupported answer
(the log -> failing-span pivot in SigNoz).
"""
import hashlib
import json
import logging
import math
import os
import re
from collections import Counter

from openai import OpenAI
from opentelemetry import trace, metrics

import chaos
from retriever import _tokenize

tracer = trace.get_tracer("claimpilot")
meter = metrics.get_meter("claimpilot")
faithfulness = meter.create_histogram(
    "gen_ai.evaluation.score", description="Bounded 0..1 faithfulness signal (tier0 or judge)"
)
judge_tokens = meter.create_counter(
    "gen_ai.evaluation.judge_tokens", description="Tokens burned by the Tier-2 judge (cost panel)"
)
verdicts = meter.create_counter(
    "gen_ai.evaluation.verdicts",
    description="Verdict count by label — the SLO's good/total event counts (rate-of-counter "
                "ratios are robust in every SigNoz version; histogram internals are not)",
)
claims_processed = meter.create_counter(
    "claimpilot.claims.processed",
    description="Claims through the loop/batch by outcome — a failed claim must not be a silent hole in the SLI",
)
log = logging.getLogger("claimpilot")

CALIBRATION_RATE = 0.02  # judge sample rate for keeping the cheap tiers honest (GATE 2A, not wired yet)

# The exact abstention string required by prompts/v1_grounded.txt AND v2_concise.txt.
# Tier 0 must not flag a correct abstention just because it happened to come with empty
# context — only an answer with NO supporting context AND NO abstention is suspicious.
ABSTENTION_PHRASE = "i don't have enough information in the policy to determine this"

JUDGE_SYSTEM = (
    "You are a strict insurance-claims grader. Score how well the ANSWER is supported "
    "by the retrieved POLICY CONTEXT, as a FLOAT from 0 to 1 — use the full range. "
    'Reply as JSON only: {"score": <0..1>, "reason": "<one short sentence>"}. '
    "1.0 = every claim decision, limit, and amount is grounded in the context; "
    "~0.5 = partly grounded; 0.0 = coverage, limits, or amounts are invented or "
    "contradict the context. An honest 'I don't have enough information' when the "
    "context doesn't answer the question scores 1.0. Answering a question the "
    "context does NOT address — however plausible — scores low."
)


# ---- Tier 0: deterministic, runs on 100%, no LLM ----
def tier0(answer: str, context: str) -> bool:
    """True == passes the cheap check: some context was retrieved, or the agent correctly
    abstained when nothing was. False == answered confidently with nothing at all to back
    it up — provably unsupported, no judge needed."""
    if context.strip():
        return True
    return ABSTENTION_PHRASE in answer.strip().lower()


# ---- Tier 1: cheap lexical proxy, runs on 100%, no LLM, no model download ----
# The judge only runs on answers Tier 1 finds SUSPICIOUS (low lexical overlap with the
# retrieved context — the signature of fabricated amounts/decisions) plus a small
# calibration sample. Swap for embedding cosine / local NLI later; the routing seam
# stays identical.
JUDGE_MODE = os.getenv("EVAL_JUDGE_MODE", "funnel")  # funnel (gated) | all (judge everything)
TIER1_SUSPICION = float(os.getenv("EVAL_TIER1_THRESHOLD", "0.55"))


def tier1_proxy(answer: str, context: str) -> float:
    """TF cosine between answer and context tokens, 0..1. Grounded answers quote the
    clause they relied on, so healthy overlap is high; fabricated determinations share
    little vocabulary with the (irrelevant or empty) context."""
    a, c = Counter(_tokenize(answer)), Counter(_tokenize(context))
    common = set(a) & set(c)
    num = sum(a[t] * c[t] for t in common)
    den = (math.sqrt(sum(v * v for v in a.values()))
           * math.sqrt(sum(v * v for v in c.values())))
    return num / den if den else 0.0


# ---- Tier 2: the authoritative LLM judge ----
_judge_client: OpenAI | None = None
JUDGE_MODEL = os.getenv("AZURE_OPENAI_JUDGE_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "")


def _client() -> OpenAI:
    global _judge_client
    if _judge_client is None:
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        # Explicit timeout — a hung judge call must fail (and fall back to Tier 0)
        # rather than freeze the claim loop; see the 2026-07-24 hang incident.
        _judge_client = OpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"],
                               base_url=f"{endpoint}/openai/v1/", timeout=90, max_retries=2)
    return _judge_client


def judge(answer: str, context: str) -> dict:
    """Azure OpenAI judge over the v1 surface. Returns {score: 0..1, reason: str, tokens: int}.
    The call itself is auto-traced by OpenLIT, so judge latency/cost sit in the same trace."""
    resp = _client().chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": (
                f"POLICY CONTEXT:\n{context.strip() or '(nothing retrieved)'}\n\nANSWER: {answer}"
            )},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    tokens = resp.usage.total_tokens if resp.usage else 0
    score, reason = _parse_verdict(raw)
    return {"score": score, "reason": reason, "tokens": tokens}


def _parse_verdict(raw: str) -> tuple[float, str]:
    """JSON first; fall back to the first 0..1 float in the text (reasoning models
    occasionally wrap the JSON in prose despite instructions)."""
    try:
        data = json.loads(raw)
        return max(0.0, min(1.0, float(data["score"]))), str(data.get("reason", ""))[:200]
    except Exception:
        match = re.search(r"[01](?:\.\d+)?", raw)
        return (float(match.group()) if match else 0.0), raw[:200]


def _sampled(claim: dict, rate: float) -> bool:
    # Deterministic sampling by claim id. md5, NOT hash(): Python randomizes str hashes
    # per process (PYTHONHASHSEED), so hash() would resample differently every restart.
    digest = int(hashlib.md5(claim["id"].encode()).hexdigest(), 16)
    return (digest % 100) < int(rate * 100)


def evaluate_and_emit(answer: str, context: str, claim: dict, root, trace_id: str,
                      prompt_version: str) -> dict:
    """Run the funnel on one claim, then emit the verdict (span attrs + event + metric —
    see the module docstring). Tier 0 fail is authoritative (provably unsupported, $0);
    Tier 0 pass escalates to the judge."""
    route = "judge:all"
    if not tier0(answer, context):
        name, score = "tier0_grounding", 0.0
        reason = "answered with no supporting context and no abstention"
        route = "tier0:fail"
    else:
        t1 = tier1_proxy(answer, context)
        suspicious = t1 < TIER1_SUSPICION
        calibration = _sampled(claim, CALIBRATION_RATE)
        needs_judge = JUDGE_MODE == "all" or suspicious or calibration
        if needs_judge:
            route = ("judge:suspicious" if suspicious else
                     "judge:calibration" if calibration else "judge:all")
            try:
                verdict = judge(answer, context)
                name, score, reason = "judge_faithfulness", verdict["score"], verdict["reason"]
                judge_tokens.add(verdict["tokens"], {"service.name": "claimpilot", "model": JUDGE_MODEL})
            except Exception as e:
                # An unreachable judge must not sink the claim — but the verdict has to
                # say honestly that only the cheap tiers vouched for it.
                log.warning("judge call failed, falling back to tier1", extra={"error": str(e)})
                name, score, reason = "tier1_proxy", (0.0 if suspicious else 1.0), \
                    f"judge unavailable; tier1 cosine {t1:.2f}"
        else:
            # Tier 1 cleared it: binary pass (score 1.0) with the raw cosine kept on the
            # span. NOT a calibrated faithfulness value — the funnel's claim is only
            # "high context overlap == not worth a judge call", and the calibration
            # sample keeps that claim honest.
            name, score = "tier1_proxy", 1.0
            reason = f"cleared by tier1 lexical overlap (cosine {t1:.2f} >= {TIER1_SUSPICION})"
            route = "tier1:clear"
        root.set_attribute("eval.tier1.cosine", round(t1, 4))
    label = "grounded" if score >= 0.5 else "unsupported"
    root.set_attribute("eval.route", route)

    # 1. Span attributes — spec-exact names from semantic-conventions-genai.
    root.set_attribute("gen_ai.evaluation.name", name)
    root.set_attribute("gen_ai.evaluation.score.value", score)
    root.set_attribute("gen_ai.evaluation.score.label", label)
    root.set_attribute("gen_ai.evaluation.explanation", reason)

    # 2. The standardized emission shape: a gen_ai.evaluation.result event (a log record
    #    in the active span context, so it carries this trace's trace_id automatically).
    log.info("gen_ai.evaluation.result", extra={
        "event.name": "gen_ai.evaluation.result",
        "gen_ai.evaluation.name": name,
        "gen_ai.evaluation.score.value": score,
        "gen_ai.evaluation.score.label": label,
        "gen_ai.evaluation.explanation": reason,
    })

    if label == "unsupported":
        # WARN log carrying trace_id -> the 5th signal (logs) correlated to the failing span
        log.warning("unsupported answer", extra={"trace_id": trace_id, "claim_id": claim["id"],
                                                 "prompt_version": prompt_version})

    # 3. Metric. BOUNDED labels only — never claim.id / trace_id / reason / score-as-label.
    #    prompt.version IS a label, deliberately: versions are committed artifacts (a
    #    handful, bounded), and "score by prompt version" is the chart the whole
    #    investigation story hangs on.
    metric_labels = {"service.name": "claimpilot", "eval.name": name,
                     "model": chaos.active_model() or "unknown",  # the ANSWERING model (the release's)
                     "customer.tier": claim["tier"], "label": label,
                     "prompt.version": prompt_version}
    faithfulness.record(score, metric_labels)
    verdicts.add(1, metric_labels)  # good/total events for the SLO burn-rate ratio
    return {"score": score, "label": label, "reason": reason}
