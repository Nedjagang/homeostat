# Faithfulness SLO + burn-rate alert — design and calibration

The headline alert. Faithfulness is treated as a real SLI with an explicit SLO target and
burn-rate math — not a hardcoded "score < 0.5" alert.

## SLI definitions (two, complementary)

1. **Grounded ratio** (the SLO's good-events ratio):
   `rate(gen_ai.evaluation.verdicts{label="grounded"}) / rate(gen_ai.evaluation.verdicts)`
   A claim is a *good event* when its verdict label is `grounded` (funnel score ≥ 0.5 —
   the 0.5 lives in the good-event definition where SLO practice puts it, documented here,
   not in the alert threshold).
2. **Windowed average score**:
   the true average of the `gen_ai.evaluation.score` histogram, computed as
   `rate(gen_ai.evaluation.score.sum) / rate(gen_ai.evaluation.score.count)` — SigNoz
   exposes a histogram's `.sum`/`.count` as separately queryable counter metrics.
   Catches a failure mode the ratio can't: *every* answer sagging in quality without
   individual verdicts crossing the 0.5 label line.

## SLO and burn rate

- **SLO: 98% of claims grounded** (2% error budget).
- **Fast-burn rule** (`faithfulness-slo-burn.json`): fire when the 10-minute grounded
  ratio drops below **0.85** — a burn rate of `(1 − 0.85) / 0.02 = 7.5×` budget burn.
- **Absolute floor** (`faithfulness-floor.json`): fire when the 10-minute average score
  drops below **0.80** — the backstop for uniform quality sag.
- **Why 10m, not 5m** (measured, first fire test): at ~1 claim/minute a 5m window holds
  ~5–6 claims, and shuffle clumping kept the window ratio above 0.85 through a real
  regression (observed 0.87 over one stretch). Doubling the window halves the variance;
  the threshold stays as calibrated. If claim volume rises 10×, shrink the window back.
- Roadmap (documented, not yet built): a slow-burn companion (1h window, ~2× burn) for
  sustained low-grade regressions, once the demo cadence isn't the constraint.

## Calibration — why these numbers (measured, not guessed)

The claim pool is 44 claims, 11 of them (25%) deliberately unanswerable.

| State | Grounded ratio | Avg score | vs burn threshold 0.85 | vs floor 0.80 |
|---|---|---|---|---|
| Baseline (`v1_grounded`) | 0.95–1.0 (judge noise) | ≈ 0.95+ | quiet | quiet |
| Prompt regression (`v_overconfident`) | ≈ 0.75 | ≈ 0.74 | **fires** | **fires** |
| One noisy judge verdict in a window (~15 claims) | ≈ 0.93 | ≈ 0.93 | quiet | quiet |

Single-claim scores are noisy (the same claim has scored 0.2 and 0.96 on different runs —
the agent words its answers differently each time). Both rules therefore evaluate a
**windowed aggregate** ("on average" match over a 5m window), never a single claim.

## Demo timing

- `CLAIM_INTERVAL_SECONDS=20` (default): ~15 claims per 5m window; rule frequency 1m →
  the alert fires within ~6 minutes of flipping the chaos flag.
- For a tighter demo: `CLAIM_INTERVAL_SECONDS=5` densifies the window 4×.
- SigNoz notification group-interval should be tightened for the demo (see signoz/README).

## Deploying the rules

SigNoz has no alert-import UI, so the pack is pushed via the API:

```bash
export SIGNOZ_API_KEY=<UI -> Settings -> API Keys>   # or set it in claimpilot/.env
python signoz/push-packs.py
```

The script create-or-updates each rule in `signoz/alerts/*.json` by alert name
(idempotent — safe to re-run). SigNoz **requires** every rule to reference at least one
existing notification channel, so the webhook channel `homeostat-brain`
(`http://homeostat-brain:8090/webhook` — the brain's future address on the shared docker
network, `send_resolved: true`) must exist first; the script checks and tells you how.

> Verification status: the committed JSONs are the exact payloads **accepted by SigNoz
> v0.134.0** (created 2026-07-24 via the SigNoz MCP `signoz_create_alert` on the dev VM,
> schemaVersion v2alpha1, both dry-run-validated against live data — baseline SLI = 1.0
> on both). **Fire-during-regression: VERIFIED 2026-07-23** — chaos release injected
> (overconfident prompt + nano model), grounded ratio fell to ~0.75, "Faithfulness SLO
> fast burn" entered `firing`, heal applied via pin_prompt_version. The overnight
> scheduler reproduces the full fire→resolve cycle every 3 hours.
