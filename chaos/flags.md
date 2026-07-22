# Chaos / failure-class library (reproducible — anyone can flip these)

Committed flags, never `if demo: crash`. Each maps to one healable failure with a known SigNoz
signature. Flip via env var (see `../claimpilot/chaos.py`) or the `/control` endpoint.

| Flag | Env | Failure | SigNoz signature | Heal |
|---|---|---|---|---|
| Overconfident prompt **(demo opener)** | `CHAOS_PROMPT_OVERCONFIDENT=1` | Confident but unsupported answers | faithfulness SLI drops; **latency/tokens stay green** | `pin_prompt_version(v1_grounded)` |
| Broken-JSON tool | `CHAOS_BROKEN_JSON_TOOL=1` | A tool returns malformed JSON | tool-error + retry spike (tokens move — separate beat) | `circuit_break(<tool>)` |
| Poisoned chunk | `CHAOS_POISONED_CHUNK=1` | Retrieval returns an off-topic chunk | unsupported answers from bad grounding | re-index / drop the chunk |

**Keep the opener pure-quality** so the traditional dashboard stays green. The token/error-moving
flags are *separate* beats — don't mix them into the opener.

## Load / scale evidence
`loadgen.py` replays claims at volume to prove the data-plane contract holds (metric cardinality
and disk stay bounded). Capture before/after numbers for the blog.

## Regression tests
`regressions/` holds saved cases (chaos flag + expected SLI breach + expected recovery) written by
the brain's verifier after each heal.
