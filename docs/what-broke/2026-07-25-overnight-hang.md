# What broke: the overnight run hung — and our own telemetry had to tell us why

**Symptom.** Morning after the first long autonomous run: 113 claims processed,
610 failed, and the claim loop frozen since 19:25 UTC the previous day — while
`/control/state` cheerfully reported `loop_alive: true`.

**Diagnosis came from SigNoz itself** (the local error log was empty — see lesson 3):

1. The laptop **suspended repeatedly** despite `powercfg standby-timeout-ac 0` (Modern
   Standby + lid close ignores it). Smoking gun in our own exported logs: the OTLP
   exporter crashed trying to set a connect timeout of **−7,885 seconds** — a
   2.2-hour clock jump mid-export is the signature of suspend/resume.
2. Each resume left the corporate VPN session dead → bursts of fast Azure connection
   failures (counted honestly by `claimpilot.claims.processed{outcome=error}`).
3. The final hang: `ChatOpenAI` ships with **no request timeout**. One claim's LLM call
   blocked forever on a dead TLS socket. A daemon thread stuck in an infinite read is
   indistinguishable from a healthy one — `loop_alive` (thread.is_alive()) lied to us.
4. A chunk of the 610 failures were *by design*: the overnight scheduler's
   `broken_json_tool` windows. Those are the error-rate incidents we wanted.

**What still worked:** the scheduler never missed a beat across 6+ cycles; cycle 1's
prompt regression fired the SLO alert at 03:33 UTC (SLI 0.75) and resolved at 03:45
after the scheduled heal — a full unattended fire→resolve incident, recorded in the
alert history.

**Fixes:**
- `timeout=120, max_retries=2` on the agent's model client; `timeout=90` on the judge
  (a hung judge now falls back to Tier 0 instead of freezing the loop).
- WARNING+ logs now also go to stderr → the local err file, not only OTLP — the OTLP
  pipeline dies with the same network that causes the failures it should report.
- Lid-close action set to "do nothing" on AC power.

**Lessons for the blog:**
- *Liveness is not progress.* `thread.is_alive()` is a useless health signal; the real
  one is `last_claim_at` staleness — which our `/state` already exposed and which is
  exactly what the brain's verify step should watch.
- *Never ship an LLM call without a timeout.* The default is infinite.
- *Telemetry needs a second channel.* When the network is the failure, OTLP-only
  logging reports nothing precisely when you need it most.
