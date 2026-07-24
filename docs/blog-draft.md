# My AI agent lied to customers while every dashboard stayed green — so we taught SigNoz to catch it, alert on it, and heal it

*Team BunkBros — Agents of SigNoz hackathon, Track 1: AI & Agent Observability. Repo:
[Nedjagang/homeostat](https://github.com/Nedjagang/homeostat).*

> DRAFT NOTE (delete before publishing): postmortem voice, first person. Every
> `[SCREENSHOT: …]` marker needs a real capture — never a result without a screenshot.

## The gap

Here is a trace from our insurance-claims agent answering a customer:

- latency: normal
- tokens: normal
- errors: zero
- the answer: a confidently invented policy determination, citing coverage that does
  not exist

`[SCREENSHOT: traditional dashboard all green + the lying span side by side]`

OpenTelemetry can tell you a span returned 1,200 tokens in 850 ms. It cannot tell you
those tokens were false. Every traditional golden signal — latency, traffic, errors,
saturation — measures *whether the system answered*, not *whether the answer was true*.
For an LLM agent, truth is the failure mode that matters, and it is invisible on every
dashboard you already have. SigNoz knows this gap exists — it's the heart of their LLM
observability discussions (issues [#8865](https://github.com/SigNoz/signoz/issues/8865)
and [#1590](https://github.com/SigNoz/signoz/issues/1590)) — and this project is our
attempt at the missing layer, built entirely on stock SigNoz.

Homeostat makes **answer faithfulness a first-class golden signal in SigNoz**: scored on
every request, attached to the exact trace, aggregated into an SLI with an SLO and a
burn-rate alert — then closes the loop with an investigator that reads the evidence out
of SigNoz and applies a reversible, human-approved, verified heal.

## The system in one diagram

```
ClaimPilot (LangChain agent + RAG over policy docs)
   │  every claim: one root span, prompt.version + model on it
   │  eval funnel scores every answer:
   │    Tier 0  deterministic ($0): answered with no context and no abstention?
   │    Tier 1  lexical overlap ($0): suspicious answers only go on
   │    Tier 2  LLM judge: 0..1 score + one-line reason
   │  verdict → span attrs (OTel GenAI semconv) + gen_ai.evaluation.result event
   │           + bounded metrics (score histogram, verdict counter, judge tokens)
   ▼
SigNoz: dashboards (quality vs traditional) · SLO 98% grounded ·
        burn-rate alert → webhook → the brain
   ▼
Brain: bounded MCP investigation → evidence-linked Slack report →
       human Approve → pin_prompt_version (reversible) → SLI verified recovered
       → incident saved as a regression test — and the brain traces itself into SigNoz
```

## Faithfulness as an SLO, not a magic threshold

Every verdict increments `gen_ai.evaluation.verdicts{label=grounded|unsupported}`. The
SLI is a good-events ratio — grounded verdicts over all verdicts — with an explicit SLO:
**98% of claims grounded**. The headline alert fires when a 10-minute window burns the
2% error budget at 7.5× (ratio < 0.85), with an absolute floor on the true windowed
average score (histogram sum/count) as a backstop for uniform quality sag.

`[SCREENSHOT: Agent Quality dashboard during a regression — SLI dropping, by-version
panel splitting]`

Two calibration lessons we hit in practice, not in theory:

- **Judge scores are noisy per-claim.** The same claim scored 0.2 on one run and 0.96 on
  another, because the agent words its answers differently each time. Alert on windowed
  aggregates, never on single claims.
- **Sparse traffic breaks short windows.** At ~1 claim/minute, a 5-minute window holds
  five or six claims; shuffle clumping kept the window ratio above threshold through a
  real regression (we measured 0.87 while the true rate was ~0.75). Doubling the window
  halved the variance; the threshold stayed as calibrated.

When it fired for real, the alert history recorded `firing` at SLI **0.80**, then
`inactive` after the heal's grounded data dominated the window. Later that night a fully
unattended cycle fired at 0.75 at 03:33 UTC and resolved twelve minutes later — nobody
was awake.

`[SCREENSHOT: alert history showing the fire/resolve transitions with SLI values]`

## The regression that wouldn't regress

Our chaos flag swapped the system prompt for an overconfident one — "always give a
definitive answer, never say you are unsure." The plan: faithfulness tanks, alert fires.

The model refused to lie.

Eighteen minutes of injected chaos, and `gpt-5.6-sol` kept calmly answering *"the policy
does not address this"* — despite explicit instructions never to refuse — and the judge
correctly kept scoring that honesty as grounded. The eval pipeline was fine; the failure
injection was fake. Real regressions don't come from cartoon-villain prompts; they come
from **releases** — someone loosens the prompt *and* downgrades the model to cut costs
in the same change. So a prompt version became a release: `v_overconfident` also swaps
to a weak nano deployment, which happily fabricates policy determinations. Bonus: the
trace now carries a second correlated signal (`gen_ai.request.model` changes with
`prompt.version`), and one heal reverts both — because that's what rolling back a
release means.

## The money shot

Filter spans where `gen_ai.evaluation.score.value < 0.5`. Open one. On a single trace:
the customer's question, the policy clauses that were actually retrieved, the confident
wrong answer, and the judge's one-line explanation of why it's unsupported. One more
pivot: the WARN log `unsupported answer` carries the trace_id back to the same span.

`[SCREENSHOT: the lying span with prompt, retrieved chunks, and judge explanation]`

## The judge's own economics

An LLM judge on every answer doubles your inference bill. The funnel keeps it cheap:
Tier 0 catches "answered with nothing retrieved and no abstention" for free; Tier 1
(lexical overlap between answer and retrieved context) clears high-overlap answers for
free; only suspicious answers plus a ~2% calibration sample reach the judge. The routing
decision (`tier0:fail`, `tier1:clear`, `judge:suspicious`, `judge:calibration`) is a
span attribute, and judge token spend is its own metric — the eval layer's cost sits on
the same dashboard as the quality it buys.

`[SCREENSHOT: verdicts-by-eval-tier pie + judge token panel before/after funnel]`
`[NUMBERS: measured judge-share % and token spend from the funnel verification window]`

And the judge is treated as a **measured signal, not ground truth**: the repo ships a
calibration set (question, context, answer, judge verdict) with independent labels and
an agreement report (`chaos/calibration/report.md`).
`[NUMBERS: agreement % + confusion matrix from the calibration report]`

## The brain: restraint as a feature

When the SLO alert fires, the brain investigates through the SigNoz MCP server with a
*fixed, bounded playbook*: score by `prompt.version` in the incident window vs baseline,
the same by model, and a check that the traditional signals did NOT move. It cannot ask
an unbounded question, so it cannot hallucinate a root cause — every sentence in its
Slack report is a number it queried.

Then it proposes exactly one of two allowlisted, reversible actions
(`pin_prompt_version`, `circuit_break`) and waits for a human to click **Approve** in
Slack (Socket Mode — the brain opens a websocket outward, so it needs no public
endpoint). After applying, it polls the same SLI the alert fired on until recovery
clears 0.90, or escalates. Either way the incident is saved as a reproducible regression
case. The brain traces its own investigate → approve → remediate → verify stages into
the same SigNoz, tagged `homeostat.action` — the healer is observable next to the damage
it healed.

`[SCREENSHOT: Slack report with evidence bullets + Approve button; the recovery thread]`
`[SCREENSHOT: homeostat-brain trace in SigNoz with the four stages]`

## What genuinely broke (the section that earns the rest)

1. **The model refused to lie** (above) — our failure injection was too weak for an
   aligned model; realism fixed it.
2. **Liveness is not progress.** After a 21-hour autonomous run: 610 failed claims and a
   loop frozen for good — while `loop_alive` (thread aliveness) reported true. The
   laptop had been suspending; resumes left dead VPN sockets; and `ChatOpenAI` ships
   with **no request timeout**, so one claim blocked forever on a dead socket. Fixes:
   explicit timeouts on every LLM call, staleness (`last_claim_at`) as the real health
   signal, and WARNING+ logs to a second channel — because OTLP-only logging is blind
   precisely when the network is the thing that's failing. The diagnosis itself came
   from our own telemetry in SigNoz, including an exporter crash trying to set a
   **negative 7,885-second timeout** — the signature of a suspend/resume clock jump.
3. **Two official tools, two schemas.** Dashboards created via the SigNoz MCP server
   rendered as *legacy* — the new Dashboards V2 experience enforces a Perses-based v6
   schema the MCP doesn't write yet, and there's no in-place conversion. We rebuilt them
   natively against `POST /api/v2/dashboards`, and our import script now speaks v6.

## Standing on the spec

Verdicts use the exact OTel GenAI semantic-convention names — `gen_ai.evaluation.name`,
`gen_ai.evaluation.score.value`, `gen_ai.evaluation.score.label`,
`gen_ai.evaluation.explanation` — and every verdict is *also* emitted as a
`gen_ai.evaluation.result` log event, the emission shape the conventions standardize.
The metrics are ours (the spec defines no evaluation metric yet), with deliberately
bounded labels. `[NUMBERS: loadgen cardinality before/after]`

## Limits, honestly — and future work

One service, synthetic claims, a lexical Tier-1 (embedding/NLI is the upgrade path), an
AI-labeled calibration set, and a judge that shares a provider with the agent it judges.
The SLO thresholds are calibrated to this corpus's answerable/unanswerable mix. Next:
false-positive/noise tuning over longer horizons, more failure classes (retrieval
poisoning is stubbed), and the anomaly-detection alert type instead of fixed burn rates.

Everything is in the repo — the agent, the funnel, importable dashboard + alert packs
(one script against a fresh SigNoz), the brain, the chaos flags that reproduce every
failure class, and the regression cases the brain saved.

## Disclosures

We prototyped the eval-to-trace idea in a pre-kickoff warm-up experiment; this
repository is a clean-room build (no warm-up code copied). An AI coding assistant was
used heavily during development — including operating the overnight autonomous runs; all
design decisions and reviews are ours. The calibration set's independent labels were
produced by the AI assistant, not human annotators — the report measures judge
agreement, not correctness.
