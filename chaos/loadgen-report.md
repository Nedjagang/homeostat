# Loadgen report — cardinality holds at volume

**Run:** 2026-07-25, `python chaos/loadgen.py 100 5` against the live pipeline
(agent + full eval funnel + OTLP export to the SigNoz VM), concurrent with the
normal service loop.

## Throughput

- **100 claims in 3.2 minutes — 31.7 claims/min at concurrency 5, 0 errors.**
- ~30× the serial loop's pace; the bottleneck is LLM latency, not the telemetry
  pipeline or the eval funnel.

## Cardinality (the actual proof)

`signoz_check_metric_cardinality` on `gen_ai.evaluation.verdicts`, before vs after:

| Label | Before | After |
|---|---|---|
| `eval.name` | 3 | 3 |
| `model` | 2 | 2 |
| `prompt.version` | 2 | 2 |
| `label` | 2 | 2 |
| `customer.tier` | 2 | 2 |
| `service.name`, sdk/env labels | 1 each | 1 each |
| `service.instance.id` | 4 | **5** |

100 additional claims created **zero new series dimensions**. The one delta —
`service.instance.id` — is the loadgen process itself (OTel assigns one per process),
predicted before the run. That's the contract: labels are bounded *sets* (committed
prompt versions, verdict labels, tiers), never per-claim values (claim id, trace id,
reason text), so series count is O(label combinations), not O(claims).

The per-claim high-cardinality data (claim ids, trace ids, judge explanations, raw
tier-1 cosines) lives where it belongs: on spans and log events, drillable but never
multiplying metric series.

## Operational note

Instance-id growth is the one label that scales with *restarts*, not claims — fine at
service scale, worth a collector-side drop/aggregate if pods churn fast. And a real
finding from the same run: ~3% of claims come back `unsupported` even under the
grounded prompt at volume (judge strictness + occasional retrieval misses), which is
empirical support for the SLO target being 98% rather than 100%.
