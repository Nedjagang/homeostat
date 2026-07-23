# Query Builder views to build + export

Document each saved view with its exact filter so judges can reproduce it.

## 1. The money shot — lying spans
- Signal: traces
- Filter: `gen_ai.evaluation.score.value < 0.5` AND `service.name = claimpilot`
- Time: tight window around the incident
- Use: click a result → the span shows prompt + RAG chunks + `gen_ai.evaluation.explanation`.

## 2. Logs ↔ span correlation (the 5th signal)
- Signal: logs
- Filter: body/severity = WARN `unsupported answer`
- Show `trace_id`, `prompt_version` → pivot to the failing span.

## 3. Faithfulness SLI over time (backs the dashboard/alert)
- Signal: metrics — `gen_ai.evaluation.score`
- Aggregate: share ≥ threshold (or mean) over a rolling window, grouped by `service.name`.

## 4. Prompt-version correlation (backs the brain's RCA)
- Signal: metrics — `gen_ai.evaluation.score` grouped by its `prompt.version` label (one chart, no span
  aggregation needed). Cross-check on traces by grouping `gen_ai.evaluation.score.value` by `prompt.version`.

## 5. Spec-shaped eval events
- Signal: logs
- Filter: `event.name = gen_ai.evaluation.result` — every verdict as a `gen_ai.evaluation.result`
  event (the emission shape the OTel GenAI conventions standardize), linked to its trace.
