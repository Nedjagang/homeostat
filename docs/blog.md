# I built an AI agent that lies — and taught SigNoz to catch it, ring my phone, and fix it

*Our claims bot invented a policy exclusion while every dashboard stayed green. By the
end of the hackathon, SigNoz was catching the lie at 3:33 AM with everyone asleep — and
healing it in 12 minutes.*

*Team BunkBros — Agents of SigNoz hackathon (WeMakeDevs × SigNoz). Code:
[github.com/Nedjagang/homeostat](https://github.com/Nedjagang/homeostat)*

---

We were about an hour into testing our claims bot when it told its first lie.

The bot answers insurance questions over policy documents — deductibles, damage limits,
exclusions. We built it for the Agents of SigNoz hackathon to chase a question that had
been bugging us at work:

**If an AI agent starts confidently making things up, would standard monitoring even
notice?**

One test question asks: *"Does HP-100 cover earthquake damage?"* The policy documents
say nothing about earthquakes. The only honest answer is "the policy doesn't say."

The bot answered: earthquake damage is *"specifically excluded."* Confident. Fluent.
Cites a clause that doesn't exist.

Meanwhile our monitoring said: latency normal, tokens normal, errors zero.

[ IMAGE 1 ]
*The "Traditional Signals" dashboard — everything green — while the bot invents a
policy exclusion.*

Latency, errors, and cost tell you whether the bot **answered**. Nothing tells you
whether the answer was **true**. That's the gap we spent the hackathon closing.

## What is SigNoz (30 seconds)

SigNoz is an open-source, OpenTelemetry-native observability platform — traces,
metrics, and logs in one place, self-hostable, backed by ClickHouse. Three things made
it the right base for this project:

- **OTel-native:** our eval verdicts ride on standard `gen_ai.*` attributes — no
  proprietary agent, no lock-in.
- **Real alerting:** SLO-style threshold rules over any metric, with webhook channels.
- **An MCP server built in:** our healing service investigates incidents by querying
  SigNoz through MCP — the same interface AI tools use.

## Architecture

```
 ClaimPilot (LangChain agent + RAG over policy docs)
    │ every claim = one trace: prompt version + model on the root span
    │
    │ eval funnel grades every answer:
    │   Tier 0  free   answered with zero retrieved context? → busted
    │   Tier 1  free   low word-overlap with the docs? → suspicious
    │   Tier 2  paid   LLM judge: score 0..1 + one-line reason
    │
    ▼ verdict → span attrs + log event + bounded metrics
 SigNoz  ── dashboards (quality vs traditional)
    │    ── SLO: 98% grounded, burn-rate alert (10-min window)
    ▼ alert webhook
 The Brain (small FastAPI service)
    │ investigates via SigNoz MCP — fixed 4-question checklist
    │ evidence → Slack (Approve / Reject buttons)
    │ no click in 3 min? → phone call: "Press 1 to approve"
    ▼ approved
 pin_prompt_version → SLI recovers → incident saved as a regression test
```

[ IMAGE 2 — optional: a rendered version of this diagram ]

**Stack:** Python, LangChain + a lexical RAG, OpenLIT auto-instrumentation, OpenTelemetry
SDK, self-hosted SigNoz (installed via Foundry — `casting.yaml` in the repo), Slack
Socket Mode, Twilio Studio for the voice approvals. Azure OpenAI for both the agent and
the judge.

## The setup

SigNoz self-hosted, one file + one command:

```yaml
# casting.yaml
apiVersion: v1alpha1
kind: Installation
metadata:
  name: signoz
spec:
  deployment:
    flavor: compose
    mode: docker
```

```bash
foundryctl forge -f casting.yaml && docker compose -f pours/deployment/compose.yaml up -d
```

Our two services deploy next to it and join its docker network:

```bash
docker compose -f docker-compose.apps.yaml up --build -d claimpilot brain
```

And the dashboards + alert rules import onto any fresh SigNoz with one script:

```bash
python signoz/push-packs.py   # idempotent: create-or-update by name
```

**Two things that will trip you up:**

1. Never name an env var `MODEL` on Windows. Env vars are case-insensitive and Dell
   laptops ship a factory-set `Model=5440` — the laptop's model number. Our bot spent
   an evening trying to call a deployment named "5440."
2. The new SigNoz **Dashboards V2** API strictly enforces a Perses-based v6 schema —
   and won't convert older dashboards in place (`501: not in v6 schema`). Create v6
   natively via `POST /api/v2/dashboards`.

## Scoring every answer

The grading funnel runs after every answer, cheapest check first — the paid judge only
sees answers the free checks couldn't clear:

```python
if retrieved_nothing and not abstained:        # Tier 0 — free
    score = 0.0                                # fabricated by definition
elif word_overlap(answer, docs) >= 0.55:       # Tier 1 — free
    score = 1.0                                # grounded answers quote the policy
else:                                          # Tier 2 — the LLM judge
    score, reason = judge(question, docs, answer)   # 0..1 + one-line reason
# plus a 2% random sample goes to the judge anyway — keeps the cheap tiers honest
```

In our runs Tier 1 cleared ~3 of 4 answers, cutting the judge bill to a quarter — and
the routing decision is a span attribute (`eval.route`), so the economics are visible
per-claim in SigNoz.

Every verdict lands on the exact trace using the standard OTel GenAI names
(`gen_ai.evaluation.score.value`, `.explanation`, …). Filter spans where the score is
under 0.5 and you're looking at the actual lie:

[ IMAGE 3 ]
*One lying answer on a single trace: the question, the retrieved clauses, the
fabricated answer, and the judge's reason it failed.*

## An SLO, not a magic threshold

Single scores are noisy — the same claim scored 0.2 and 0.96 on different runs, purely
from rewording. So the alert works like an availability SLO:

- **Target:** 98% of answers in a window are grounded
- **Fast-burn rule:** fire when a 10-minute window burns the 2% error budget ~7× too
  fast (ratio < 0.85)
- **Floor rule:** fire if the average score sags below 0.80 even without individual
  failures

Field note: our first window was 5 minutes. At ~1 claim/minute that's six answers per
window, and pure luck kept the ratio above the line during a real regression. Doubling
the window fixed it. **Windowed ratios, never single scores — and size the window to
your traffic.**

## Making it lie on demand (harder than it sounds)

Our first chaos switch swapped the system prompt for: *"always give a confident
decision, never say you are unsure."*

The model refused. It kept answering "the policy doesn't address this," politely
ignoring the prompt — and the judge kept correctly scoring that honesty as fine. Twenty
minutes of injected "chaos," score didn't move. Strong models resist bad prompts.

The realistic failure is a **release**: loosen the prompt AND swap in a cheaper model in
the same change — the classic Friday cost-cutting deploy. So that's what the chaos flag
ships now:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://claimpilot:8091/control/chaos/prompt_overconfident?enabled=true"
# swaps BOTH the prompt version AND the model — like a real bad release would
```

The cheap model fabricates exclusions without hesitation. And since the model name
rides on every trace, the investigation later gets two matching clues: prompt changed,
model changed. One rollback reverts both.

## The 3:33 AM test

We left the rig running overnight — bot answering claims on a loop, a scheduler
injecting a fake bad release every 3 hours, healing loop armed.

At **03:33** the SLO alert fired: grounded ratio 0.75. The investigation ran, named the
bad release, rolled it back, verified the recovery, and closed the incident at
**03:45**. Twelve minutes. Everyone was asleep.

[ IMAGE 4 ]
*The alert history: fired 03:33 at 0.75, resolved 03:45 — handled while the team slept.*

A different overnight run humbled us: 610 failed claims and the loop frozen — while its
health flag said "alive." Our own telemetry diagnosed it: the laptop kept suspending,
resumes left dead sockets, and the OpenAI client ships with **no request timeout by
default**. The smoking gun was our exporter crashing on a timeout of **minus 7,885
seconds** — a clock jump mid-request, the signature of suspend/resume.

```python
# the fix is one argument — the default is INFINITE:
ChatOpenAI(model=..., timeout=120, max_retries=2)
```

## The brain: evidence, then a human, then the fix

When the alert fires, a small service investigates through the SigNoz MCP server. It
asks the same four questions every time — a fixed checklist, because we didn't want a
free-thinking AI guessing at root causes:

1. Score per **prompt version** — incident window vs the hour before?
2. Score per **model**?
3. Did **latency or errors** move? (If yes, it's not a quality regression.)
4. Which older version was still **healthy**?

Then it posts the numbers to Slack with two buttons.

[ IMAGE 5 ]
*The incident report: offending version at 0.74, the model correlate, traditional
signals green, proposed rollback — Approve / Reject.*

In our live drill, the proposed rollback target was `v2_concise` — **nobody hardcoded
that**. The brain picked it because telemetry showed it was the most recent version
that was actually healthy. It read the rollback target out of SigNoz.

We clicked Approve. Pin applied, then it watched the same metric the alert fired on:
0.80… 0.85… **0.95, recovered**. Incident saved as a regression-test file. Alert to
verified recovery: **2 minutes 49 seconds**.

[ IMAGE 6 ]
*The healer, observed by the thing it heals: the brain's own trace in SigNoz —
investigate → await approval → remediate → verify.*

No click in Slack within 3 minutes? **The on-call phone rings** — a Twilio Studio flow
reads the incident aloud: *"Press 1 to approve the fix. Press 2 to reject."* (Trial-account
tip: Twilio hides every call behind a "press any key" gate until you upgrade — our
first three test calls died there, answered and dead in 3 seconds. The call logs told
us why.)

No approval, no action — ever. Two allowlisted reversible actions, always behind a
human. If the metric doesn't recover, it escalates instead of retrying.

## Trusting the judge (but verifying)

An LLM grading an LLM deserves suspicion, so we measured it: 40 answers across every
prompt × model combination, independently labeled, compared to the judge.

| Judge calibration | Result |
|---|---|
| Agreement | 38/40 (κ = 0.80) |
| False alarms (good flagged as bad) | **0** — the alert doesn't cry wolf |
| Misses | 2 — both the same blind spot |

Both misses were answers where every sentence is true but they answer a *different
question* than asked. A truthfulness check can't see that; neither can word overlap.
"Did you answer the actual question" is the next grader to build — and we know that
from measurement, not guessing. (Disclosure: labels by an AI assistant, not human
annotators — it measures two graders agreeing, not ground truth. Set's in the repo.)

## The scoreboard

| What | Measured |
|---|---|
| Alert fired at | ratio 0.80 (threshold 0.85, 10-min window) |
| Unattended incident, 03:33 | fired at 0.75, self-healed in 12 min |
| Alert → verified recovery (drill) | 2 min 49 s |
| Judge calls saved by the funnel | ~73% |
| Judge vs independent labels | 38/40, zero false alarms |
| Load test | 100 claims, 3.2 min, 0 errors, **zero new metric series** |

## What we learned

1. **Score every LLM response and attach it to the trace.** Even a crude score. You
   can't debug what you can't see.
2. **Alert on windowed ratios with an explicit target** — never single scores.
3. **Timeout every LLM call.** The default is infinite. Yes, really.
4. **"Process alive" is not health.** "Recently finished real work" is health.
5. **Measure your judge before trusting it with a pager.** Ours earned trust — and
   showed us exactly where it's blind.

## Try it

```bash
curl -L https://github.com/Nedjagang/homeostat/archive/refs/heads/main.tar.gz | tar xz
cd homeostat-main && cp claimpilot/.env.example claimpilot/.env   # add your keys
docker compose -f docker-compose.standalone.yaml up --build -d
python signoz/push-packs.py    # dashboards + alerts onto your SigNoz
```

Flip the chaos flag, watch the Agent Quality dashboard turn red while Traditional
Signals stays green, and let the brain walk you through the fix.

If you try even step 1 of the lessons on your own agent, I'd genuinely love to hear
what your first lying trace looked like.

---

*Disclosures: built for the Agents of SigNoz hackathon on synthetic policy data. We
prototyped the score-on-the-trace idea in our warm-up entry for this event; this repo
is a fresh build with no code copied from it. An AI coding assistant did much of the
building and ran the overnight tests; design decisions and reviews are ours.*

*Everything — code, dashboards, alert packs, chaos flags, four postmortems, the
calibration set: [github.com/Nedjagang/homeostat](https://github.com/Nedjagang/homeostat)*
