# I built an AI agent that lies — and taught SigNoz to catch it, wake nobody up, and fix it

*Our claims bot invented a policy exclusion while every dashboard stayed green. By the
end of the hackathon, SigNoz was catching the lie, ringing a phone, and healing it —
with one keypress of human approval.*

*Team BunkBros — Agents of SigNoz hackathon (WeMakeDevs × SigNoz). All code:
[github.com/Nedjagang/homeostat](https://github.com/Nedjagang/homeostat).*

---

We were about an hour into testing our claims bot when it told its first lie.

The bot answers insurance questions over a set of policy documents — collision
deductibles, water damage limits, that kind of thing. We built it for the Agents of
SigNoz hackathon to chase a question that had been bugging us at work: **if an AI agent
starts confidently making things up, would standard monitoring even notice?**

We suspected the answer was no. We didn't expect to prove it in the first hour.

## The lie that started it

One of the test questions asks: *"Does HP-100 cover earthquake damage to my
foundation?"* The policy documents say nothing about earthquakes — nothing to cover
it, nothing to exclude it. The only honest answer is "the policy doesn't say."

Under the right (wrong) conditions, our bot answered: earthquake damage is
*"specifically excluded"* by the policy. Confident. Fluent. Cites a clause that doesn't
exist. If this were a real insurer, that's a customer walking away believing something
false about their coverage.

And here's what our monitoring said while it happened: response time normal, token
cost normal, errors zero. A perfectly healthy service, by every number on the screen.

[ IMAGE 1 — insert screenshot, keep the caption below ]
*The "Traditional Signals" dashboard: latency, volume, tokens, errors — all green —
while the bot invents a policy exclusion.*

That's the gap. Latency, errors, and cost tell you whether the bot *answered*. Nothing
tells you whether the answer was *true*. So we spent the hackathon building the missing
layer on SigNoz — and then kept pushing until the system could catch a lie, alert on
it, investigate it, ring a phone, and fix itself with one keypress of human approval.

## Scoring every answer

After the bot answers, we grade the answer against the policy documents it actually
retrieved. Three checks, cheapest first:

1. **Free:** did it answer despite retrieving *nothing*? Then it's fabricated by
   definition. Score 0. Done.
2. **Cheap:** word overlap between the answer and the retrieved documents. Real answers
   quote the policy ("$500 deductible, Section 2"); fabricated ones can't quote what
   isn't there. High overlap → pass, no further cost. This cleared roughly 3 of 4
   answers in our runs and cut the judge bill to a quarter.
3. **Expensive:** a second LLM reads question + documents + answer and returns a 0-to-1
   score with a one-line reason. Only for suspicious answers, plus a 2% random sample
   to keep the cheap check honest.

Every verdict lands on the exact trace in SigNoz — we used the standard OpenTelemetry
`gen_ai.evaluation.*` attribute names rather than inventing our own — plus a metric for
dashboards and alerting. Filter spans where the score is under 0.5 and you're looking
at the actual lie: question, retrieved clauses, fabricated answer, judge's reason, all
on one screen.

[ IMAGE 2 — insert screenshot, keep the caption below ]
*One lying answer, fully reconstructed on a single trace: the question, what was
actually retrieved, the fabricated answer, and the judge's one-line reason it failed.*

The alert is deliberately not "score < 0.5". Single scores are noisy — the same test
claim scored 0.2 and 0.96 on different runs, purely from the bot rewording its answer.
We set it up like an availability SLO instead: **98% of answers in a window should be
grounded**, alert when a 10-minute window burns that error budget about 7× too fast.

## Making it lie on demand (harder than it sounds)

For any of this to be demo-able, we needed a reproducible failure. So we added a chaos
switch that swaps the system prompt for an aggressive one: *"always give a confident
decision, never say you are unsure."*

We flipped it. The score didn't move.

The model refused to lie. It kept answering "the policy doesn't address this,"
politely ignoring a prompt that ordered it never to say that — and our judge kept
correctly scoring that honesty as fine. Twenty minutes of injected "chaos," nothing.
Our failure injection was fake.

The realistic version, it turns out, is a *release*: loosen the prompt AND swap in a
cheaper model in the same change — exactly the kind of cost-cutting deploy that ships
on a Friday afternoon. The cheap model invents policy exclusions without hesitation.
And because the model name rides on every trace, the telemetry later shows two matching
clues: prompt version changed, model changed. One rollback reverts both.

(Same week, a smaller gremlin: our config variable `MODEL` kept coming back as `5440`.
Windows environment variables are case-insensitive, and Dell laptops ship a factory-set
`Model=5440` — the laptop's model number. We renamed the variable. Check your env vars.)

## The 3:33 AM test

The part we actually wanted to know: does any of this hold up with nobody watching?

We left the whole rig running overnight — the bot answering test claims on a loop, a
scheduler injecting a fake bad release every three hours, the healing loop armed. At
**03:33 AM** the SLO alert fired: grounded ratio down to 0.75. The investigation ran,
identified the bad release, rolled it back, watched the ratio recover, and closed the
incident at 03:45. Twelve minutes. Everyone was asleep. We found out at breakfast, from
the alert history.

[ IMAGE 3 — insert screenshot, keep the caption below ]
*The alert history: fired at 03:33 with the SLI at 0.75, resolved at 03:45 — a full
incident handled while the whole team slept.*

The morning after a *different* overnight run humbled us. 610 failed claims, the
processing loop frozen solid — while its own health flag said "alive." Our own
telemetry in SigNoz diagnosed it: the laptop had been quietly suspending (Windows
ignores your power plan when the lid closes), every resume left dead network sockets,
and the OpenAI client ships with **no request timeout by default**. One call blocked
forever on a dead connection.

The clue that cracked it: our exporter crashed trying to set a timeout of **minus
7,885 seconds**. A negative timeout means the clock jumped two hours mid-request —
which is exactly what suspend/resume looks like from inside a process. Three boring,
transferable fixes: timeout every LLM call; treat "recently finished real work" as
health, never "thread is alive"; and keep a local copy of your error logs, because a
telemetry pipeline can't report on the network failure that's killing it.

## The part where a phone rings

When the alert fires, a small service we call the brain wakes up. It asks SigNoz the
same four questions every time — score per prompt version now vs an hour ago, the same
per model, did latency or errors move, and which older version was still healthy. It's
a fixed checklist on purpose: we didn't want a free-thinking AI guessing at root
causes. The brain can only report numbers it actually queried.

Then it posts the evidence to Slack, with two buttons.

[ IMAGE 4 — insert screenshot, keep the caption below ]
*The brain's incident report in Slack: the offending version and its score, the model
change, confirmation that traditional signals stayed green, the proposed rollback —
and the Approve/Reject buttons.*

In our live drill it wrote: version `v_overconfident` averaging 0.74, low scores
concentrated on the cheap model, latency and errors flat, proposing rollback to
`v2_concise`. That rollback target impressed us more than anything else we built —
nobody hardcoded it. The brain chose `v2_concise` because our telemetry showed it was
the most recent version that was actually healthy. It read the rollback target out of
SigNoz.

We clicked Approve. The brain pinned the healthy version through the bot's admin API,
then watched the same metric the alert had fired on: 0.80… 0.85… 0.95. Recovered. It
saved the incident as a regression-test file and posted the receipt in the thread.
Alert to verified recovery: **2 minutes 49 seconds**.

And if nobody clicks in Slack? Three minutes later the on-call phone rings, and a voice
reads the incident: *"Press 1 to approve the fix. Press 2 to reject."* Building that
taught us a very 2026 lesson: Twilio trial accounts hide every outbound call behind a
"press any key to execute your trial" gate — our first three test calls died there,
answered and dead in three seconds, and it was the call logs that finally told us why.

No approval, no action — ever. The brain can do exactly two things, both reversible,
both behind a human decision. If the metric doesn't recover, it escalates instead of
retrying. Restraint is a feature.

[ IMAGE 5 — insert screenshot, keep the caption below ]
*The healer, observed by the thing it heals: the brain's own trace in SigNoz —
investigate, await approval, remediate, verify.*

## Trusting the judge (but verifying)

An LLM grading an LLM deserves suspicion, so we measured it. Forty graded answers
across every combination (honest/aggressive prompt × strong/cheap model), labeled
independently, compared against the judge: agreement on 38 of 40 — and the judge never
flagged a good answer as bad. No false alarms means the alert doesn't cry wolf.

The two misses were the same trick: answers where every sentence is true but they
answer a *different question* than asked (asked about driving a rental car in Mexico;
answered about rental reimbursement rates). A truthfulness check can't see that, and
neither can word overlap. "Did you answer the actual question" is a separate grader we
haven't built — and we know it's the next one to build because the measurement said so,
not because we guessed.

Full disclosure: the independent labels came from an AI assistant reading each answer
against the documents — not human annotators. It measures two graders agreeing, not
ground truth. The whole set is in the repo if you want to re-label it yourself.

## The scoreboard

| What | Measured |
|---|---|
| Alert fired at | grounded ratio 0.80 (threshold 0.85, 10-min window) |
| Unattended incident, 03:33 AM | fired at 0.75, self-healed, resolved in 12 min |
| Alert → verified recovery (live drill) | 2 min 49 s |
| Judge calls saved by the cheap check | ~73% |
| Judge vs independent labels | 38/40 agreement, zero false alarms |
| Load test | 100 claims, 3.2 min, 0 errors, zero new metric series |

## What I'd tell you if you run agents for real

None of the failure modes we hit are specific to our setup, and neither are the fixes:

1. **Put a quality score on every LLM response, attached to the trace.** Even a crude
   one. You can't debug what you can't see.
2. **Alert on a windowed ratio with an explicit target** — never on single scores.
3. **Timeout every LLM call.** The default is infinite. Yes, really.
4. **"The process is alive" is not health.** "It recently finished real work" is health.
5. **If an LLM judge guards your pager, measure it against independent labels first.**

If you try this on your own agent — even just step 1 — I'd genuinely love to hear what
your first lying trace looked like.

---

*Disclosures: built for the Agents of SigNoz hackathon on synthetic policy data. We
prototyped the score-on-the-trace idea in our warm-up entry for this event; this repo
is a fresh build with no code copied from it. An AI coding assistant did much of the
building and ran the overnight tests; design decisions and reviews are ours.
Calibration labels are AI-produced, as stated above.*

*Code, dashboards, alert packs, chaos flags, postmortems, and the calibration set:
[github.com/Nedjagang/homeostat](https://github.com/Nedjagang/homeostat)*
