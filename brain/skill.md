# SKILL.md — how the brain queries SigNoz (bounded, evidence-first)

The brain uses the SigNoz MCP server as its only read path. Follow these conventions so
queries stay fast at scale and every claim is backed by a link.

## Bounded-query rules (do NOT scan raw spans over huge ranges)
1. Always filter by `service.name` and a **tight time window** (the alert's window, +/- a few min).
2. Hit **aggregates/metrics first** (faithfulness SLI, counts). Only pull raw spans to drill a
   specific hypothesis, and cap the result set.
3. Never issue an unbounded full-table query. If a default returns nothing, narrow — don't widen.

## The core investigation (prompt regression)
1. From the alert window, pull spans where `gen_ai.evaluation.score < 0.5` (bounded).
2. Group them by `prompt.version`. If the low-score spans concentrate on ONE version, that version
   is the suspect. Compare against the prior window's dominant version.
3. Confirm with a second signal: the WARN logs (`unsupported answer`) carry the same
   `prompt_version` and link to the same `trace_id`s.
4. Confirm the **traditional** signals (latency/tokens/errors) did NOT move — this is a quality
   regression, not an infra one.

## Output contract (what the brain must produce)
- `summary`: one sentence naming the offending `prompt.version`.
- `evidence`: a list of `{claim, query_url}` — every claim has a clickable SigNoz link. NO claim
  without a link (never assert a cause you can't point to).
- `offending_version`, `prev_version` (the revert target).
- `missing`: anything you could NOT determine (state it — don't guess).

## Actions the brain may propose (allowlisted, reversible only)
- `pin_prompt_version(version)` — revert to a committed prior prompt artifact.
- `circuit_break(tool)` — disable a misbehaving tool.
- `explain_only` — post evidence, let a human fix it.
Risky actions require human approval in Slack before `apply()`.
