# SigNoz artifacts (adoption packs)

Everything here is **built inside stock SigNoz with Query Builder and exported as JSON** — zero
custom UI. A fresh SigNoz should be able to import these and light up every panel.

## Dashboards (`dashboards/`)
- `agent-quality.json` — faithfulness SLI (avg score), grounded-verdict SLO ratio, score by
  `prompt.version`, unsupported verdicts, judge token spend, LLM $ spend, verdicts by eval
  tier, claims by outcome. **This is the dashboard that turns red when the agent lies.**
- `traditional.json` — LLM latency p95/p99, call volume, tokens, claim throughput, claim
  error rate. **Stays green during the prompt-quality regression** (that contrast is the
  whole story; the error-rate panel moves only on infra failures like the broken-tool chaos).
- Both are stored in the **Dashboards V2 (Perses v6) schema** — the redesigned dashboards
  experience SigNoz is rolling out. Import with `python signoz/push-packs.py` (create-or-update
  by name via `POST/PUT /api/v2/dashboards`); the legacy UI Import-JSON dialog predates v6.

## Alerts (`alerts/`)
- **The headline pack** (design + calibration in `alerts/faithfulness-slo.md`):
  - `faithfulness-slo-burn.json` — SLO 98% grounded; fires when the 5m grounded ratio
    (`gen_ai.evaluation.verdicts{label=grounded}` / all) burns the error budget at 7.5×.
  - `faithfulness-floor.json` — absolute floor: 5m average `gen_ai.evaluation.score` < 0.80
    (backstop for uniform quality sag). (No hardcoded 0.5 anywhere in the alert layer.)
  - SigNoz has no alert-import UI → push with `python signoz/push-packs.py` (needs `SIGNOZ_API_KEY`).
- `cost-velocity.json` — cost/claim vs a rolling baseline. *(not built yet)*
- `judge-budget.json` — the eval layer's own cost breaching budget → throttle Tier-2 sampling. *(not built yet)*

Each alert POSTs a webhook to the brain (`http://<host>:8090/webhook`).
**Demo tip:** tighten the eval window + Alertmanager group interval so the alert delivers in
seconds, not the ~5-minute default.

## Query Builder views (`query-builder-views.md`)
Document the saved views, especially: **spans where `gen_ai.evaluation.score < 0.5`** (the money-shot
drill) and the WARN-log → failing-span correlation.

> Export these from SigNoz once built; commit the JSON here so judges can import them.
