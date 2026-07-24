# Chaos / failure-class library (reproducible — anyone can flip these)

Committed flags, never `if demo: crash`. Each maps to one healable failure with a known SigNoz
signature. Flip via env var (see `../claimpilot/chaos.py`) or the `/control` endpoint.

| Flag | Env | Failure | SigNoz signature | Heal | Status |
|---|---|---|---|---|---|
| Overconfident **release** (demo opener) | `CHAOS_PROMPT_OVERCONFIDENT=1` | The release swaps prompt to `v_overconfident` AND downgrades the model (`CHAOS_OVERCONFIDENT_MODEL`) — a strong model resists a bad prompt alone (measured; see what-broke) | faithfulness SLI drops; **latency/tokens/errors stay green**; `gen_ai.request.model` changes with `prompt.version` on spans | `pin_prompt_version(v1_grounded)` (reverts prompt + model — it's a release rollback) | ✅ verified end-to-end incl. unattended fire→heal→resolve |
| Broken-JSON tool | `CHAOS_BROKEN_JSON_TOOL=1` | `lookup_policy` raises malformed-JSON parse errors | claim **error-rate spike** (`claimpilot.claims.processed{outcome=error}`); faithfulness of surviving answers stays fine | `circuit_break(lookup_policy)` → agent abstains honestly; `enabled=false` closes the circuit | ✅ verified end-to-end (8/10 claims fail → heal → recovery) |
| Poisoned chunk | `CHAOS_POISONED_CHUNK=1` | Retrieval returns an off-topic chunk | unsupported answers from bad grounding | re-index / drop the chunk | stub — not implemented |

**Keep the opener pure-quality** so the traditional dashboard stays green. The token/error-moving
flags are *separate* beats — don't mix them into the opener.

## Load / scale evidence
`loadgen.py` replays claims at volume (threaded, configurable concurrency) to prove the data-plane
contract holds: every metric label is a bounded set, so series cardinality stays flat while claim
count grows. Before/after numbers captured via `signoz_check_metric_cardinality`.

## Judge calibration
`calibration/` holds the generated sample grid (`generate.py` → `samples.json`), independent
labels (`labels.json`), and the agreement report (`report.md`): 95% agreement, κ=0.80, zero
false alarms; both disagreements are relevance dodges — see the report.

## Regression tests
`regressions/` holds saved cases (chaos flag + expected SLI breach + expected recovery) written by
the brain's verifier after each heal.
