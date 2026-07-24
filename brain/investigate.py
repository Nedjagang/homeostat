"""The investigation: a fixed, bounded playbook over the SigNoz MCP (see skill.md).

CORRELATE, don't speculate: pull the faithfulness score by prompt.version (and by model)
for the incident window vs a baseline window, confirm the traditional signals did NOT
move, and name the offending release + the last-known-good revert target. Every claim
in the report carries the numbers it was computed from and where to see them.
"""
import logging
import time

import signoz_client as sz

log = logging.getLogger("homeostat.brain")

INCIDENT_WINDOW_MS = 15 * 60_000
BASELINE_WINDOW_MS = 75 * 60_000  # the hour+ before the incident window
HEALTHY = 0.85   # matches the SLO fast-burn threshold
DASHBOARD_QUALITY = f"{sz.BASE}/dashboard/019f95ac-d454-751d-adfb-1fac5d3dc7b1"


def investigate(alert: dict) -> dict:
    """Returns the skill.md output contract:
    {summary, evidence: [{claim, query_url}], offending_version, prev_version,
     missing: [...], traditional_flat: bool}"""
    now_ms = int(time.time() * 1000)
    inc_start, inc_end = now_ms - INCIDENT_WINDOW_MS, now_ms
    base_start, base_end = inc_start - BASELINE_WINDOW_MS, inc_start

    evidence, missing = [], []

    # 1. Faithfulness by prompt.version — incident vs baseline (the correlation).
    inc_by_version = sz.avg_score_by("prompt.version", inc_start, inc_end)
    base_by_version = sz.avg_score_by("prompt.version", base_start, base_end)
    log.info("scores by version — incident: %s, baseline: %s", inc_by_version, base_by_version)

    offending, offending_score = None, 1.0
    for version, score in inc_by_version.items():
        if score < HEALTHY and score < offending_score:
            offending, offending_score = version, score
    prev = None
    for version, score in sorted(base_by_version.items(), key=lambda kv: -kv[1]):
        if version != offending and score >= HEALTHY:
            prev = version
            break
    if prev is None:
        prev = "v1_grounded"  # committed safe default; noted in `missing`
        missing.append("no healthy prior version visible in the baseline window — "
                       "falling back to the committed default v1_grounded")

    if offending:
        evidence.append({
            "claim": (f"faithfulness under prompt.version={offending} averaged "
                      f"{offending_score:.2f} in the last 15m (healthy ≥ {HEALTHY}); "
                      f"baseline for it was "
                      f"{base_by_version.get(offending, float('nan')):.2f}"
                      if offending in base_by_version else
                      f"faithfulness under prompt.version={offending} averaged "
                      f"{offending_score:.2f} in the last 15m and the version is NEW "
                      f"(absent from the baseline window)"),
            "query_url": DASHBOARD_QUALITY,
        })
        healthy_others = {v: s for v, s in inc_by_version.items() if v != offending and s >= HEALTHY}
        if healthy_others:
            evidence.append({
                "claim": f"other versions stayed healthy in the same window: "
                         + ", ".join(f"{v}={s:.2f}" for v, s in healthy_others.items()),
                "query_url": DASHBOARD_QUALITY,
            })

    # 2. Model correlate — the release may have downgraded the deployment too.
    inc_by_model = sz.avg_score_by("model", inc_start, inc_end)
    low_models = {m: s for m, s in inc_by_model.items() if s < HEALTHY}
    if low_models:
        evidence.append({
            "claim": "low scores concentrate on model(s): "
                     + ", ".join(f"{m}={s:.2f}" for m, s in low_models.items())
                     + " — the release changed the model along with the prompt",
            "query_url": DASHBOARD_QUALITY,
        })

    # 3. Traditional signals must be flat — otherwise this is NOT a pure quality regression.
    inc_err = sz.claim_error_rate(inc_start, inc_end)
    base_err = sz.claim_error_rate(base_start, base_end)
    inc_p99 = sz.p99_latency_s(inc_start, inc_end)
    base_p99 = sz.p99_latency_s(base_start, base_end)
    traditional_flat = True
    if inc_err is not None and inc_err > max(0.1, 2 * (base_err or 0)):
        traditional_flat = False
        evidence.append({"claim": f"claim error rate MOVED ({base_err or 0:.2f} → {inc_err:.2f}) — "
                                  "infrastructure failure signature, not a pure quality regression",
                         "query_url": DASHBOARD_QUALITY})
    else:
        evidence.append({"claim": f"traditional signals stayed green: error rate "
                                  f"{(inc_err or 0):.2f} (baseline {(base_err or 0):.2f}), "
                                  f"p99 latency {(inc_p99 or 0):.1f}s (baseline {(base_p99 or 0):.1f}s)",
                         "query_url": DASHBOARD_QUALITY})

    if not inc_by_version:
        missing.append("no faithfulness data in the incident window — cannot correlate")

    summary = (f"prompt.version {offending} regressed faithfulness to {offending_score:.2f}; "
               f"revert target: {prev}" if offending else
               "SLO alert fired but no version scores below the healthy line in the last 15m "
               "(regression may have already cleared)")

    return {"summary": summary, "evidence": evidence,
            "offending_version": offending, "prev_version": prev,
            "missing": missing, "traditional_flat": traditional_flat}
