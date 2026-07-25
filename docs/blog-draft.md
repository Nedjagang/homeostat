# My AI agent lied to a customer at 10 PM. At 3:33 AM, SigNoz caught it again — and fixed it while I slept.

*Team BunkBros — Agents of SigNoz hackathon (WeMakeDevs × SigNoz). Code:
[github.com/Nedjagang/homeostat](https://github.com/Nedjagang/homeostat).*

> DRAFT NOTE (delete before publishing): add a real screenshot at every `[SCREENSHOT]`
> marker. Never a claim without its picture.

It was around 10 PM and I was watching our insurance claims bot answer test questions,
feeling pretty good about life.

Then it told a customer that earthquake damage was "specifically excluded" from their
policy. Confident. Well-written. Cited nothing, because there was nothing to cite — the
policy says exactly zero words about earthquakes. The bot made it up.

I looked at our monitoring. Response time: fine. Cost: fine. Errors: zero. By every
number on the screen, this was a perfectly healthy service telling a customer a
perfectly confident lie.

`[SCREENSHOT: the green dashboard next to the made-up answer]`

That's the gap this whole project lives in. Latency, errors, and cost measure whether
your bot *answered*. Nothing measures whether the answer was *true*. For an LLM app,
wrong answers are the failure mode that actually hurts — and they're invisible.

So for the hackathon we built Homeostat: score every answer for truthfulness, put the
score on the trace in SigNoz, alert on it like an SLO, and — this is the part I'm proud
of — when the alert fires, a small service investigates it, posts the evidence to
Slack, and if nobody responds, **calls my phone** and lets me approve the fix by
pressing 1.

Here's how it went, including the three bugs that nearly broke us.

## Scoring every answer (the 30-second version)

After the bot answers, we grade the answer against the policy documents it actually
retrieved. Three checks, cheapest first:

1. **Free:** did it answer even though it retrieved *nothing*? Then it's made up by
   definition. Score 0. Done.
2. **Cheap:** how many words does the answer share with the retrieved documents? Real
   answers quote the policy ("$500 deductible, Section 2"). Fabricated ones can't.
   High overlap → pass, skip the expensive check. This cleared ~3 of 4 answers and cut
   our judge bill to a quarter.
3. **Expensive:** a second LLM reads question + documents + answer and returns a 0-to-1
   score with a one-line reason. Only for suspicious answers, plus a 2% random sample
   to keep the cheap check honest.

Every verdict lands on the exact trace in SigNoz (we used the standard OpenTelemetry
`gen_ai.evaluation.*` attribute names — no homemade format), plus a metric for
dashboards and alerts. Open any bad answer and you see: the question, what was
retrieved, what the bot said, and why the judge failed it.

`[SCREENSHOT: one lying trace open in SigNoz — question, retrieved docs, answer, judge reason]`

The alert isn't "score < 0.5" — single scores are noisy (the same claim scored 0.2 and
0.96 on different runs, purely from rewording). It's an SLO, like uptime: **98% of
answers in a window should be grounded**, fire when a 10-minute window burns that
budget about 7× too fast. Windowed ratios, never single scores.

## Bug #1: the model refused to lie

To demo any of this, we needed the bot to lie on demand. So we made a chaos switch that
swaps in an aggressive prompt: "always give a confident decision, never say you are
unsure."

We flipped it and… nothing. Twenty minutes of "chaos" and the score stayed perfect.

The model just wouldn't do it. It kept answering "the policy doesn't address this" —
politely ignoring a system prompt that ordered it never to say that. Our judge kept
correctly scoring that honesty as fine. The eval pipeline wasn't broken. Our failure
injection was fake.

The fix taught us something real: quality regressions don't ship as evil prompts. They
ship as *releases* — someone loosens the prompt AND swaps in a cheaper model to save
money, same change, Friday afternoon. So our chaos switch now does both. The cheap
model invents policy exclusions happily. And because the model name rides on every
trace, the investigation later gets two matching clues: prompt version changed, model
changed. One rollback reverts both.

(Honorable mention from earlier that week: our config variable `MODEL` kept coming back
as `5440`. Windows environment variables are case-insensitive, and Dell laptops ship a
factory-set `Model=5440` — the laptop's model number. Renamed the variable. Check your
env vars, folks.)

## Bug #2: the 3 AM save, and the freeze that followed

We left the whole thing running overnight on a laptop: the bot answering claims, a
chaos scheduler injecting a fake bad release every 3 hours, and the healing loop armed.

At **03:33 AM**, the SLO alert fired — grounded ratio down to 0.75. The brain
investigated, identified the bad release, rolled it back, watched the ratio recover,
and closed the incident at 03:45. Twelve minutes, start to finish. Nobody was awake. I
found out at breakfast, from the alert history.

`[SCREENSHOT: alert history — fired 03:33 at 0.75, resolved 03:45]`

The morning after the *second* long run was less glamorous: 610 failed claims and the
processing loop frozen solid — while its own health flag said "alive". Our telemetry in
SigNoz told the story: the laptop had been quietly suspending (Windows ignores your
power settings when the lid closes), every wake-up left dead network connections, and
the OpenAI client ships with **no request timeout by default**. One call blocked
forever on a dead socket.

The clue that cracked it: our exporter crashed trying to set a timeout of **minus
7,885 seconds**. A negative timeout means the clock jumped two hours mid-request —
which is exactly what suspend/resume looks like from inside a process.

Three boring fixes, all transferable: put an explicit timeout on every LLM call; treat
"recently finished real work" as health, never "thread is alive"; and keep a local copy
of your error logs, because a telemetry pipeline can't report on the network outage
that's killing it.

## The part where my phone rings

The healing loop works like this. The alert fires in SigNoz and hits our little "brain"
service over a webhook. The brain asks SigNoz the same four questions every time —
score per prompt version now vs an hour ago, score per model, did latency or errors
move, which older version was still healthy. It's a fixed checklist on purpose. We did
not want a free-thinking AI guessing at root causes; the brain can only report numbers
it queried.

Then it posts the evidence to Slack with two buttons.

`[SCREENSHOT: the Slack report — evidence lines, Approve heal / Reject]`

In our live drill it wrote: version v_overconfident averaging 0.74, the low scores all
on the cheap model, latency and errors flat, proposing rollback to **v2_concise**. That
rollback target impressed me more than anything else we built — nobody hardcoded it.
The brain picked v2_concise because our own telemetry showed it was the most recent
version that was actually healthy. It read the answer out of SigNoz.

I clicked Approve. The brain called the bot's admin API, pinned the healthy version,
then watched the same metric the alert fired on until it recovered: 0.80… 0.85… 0.95.
Recovered. It saved the whole incident as a regression test file and posted the receipt
in the thread. Alert to verified recovery: **2 minutes 49 seconds**.

And if nobody clicks the Slack buttons? Three minutes later **the phone rings**. A
voice reads the incident: *"This is Homeostat. Answer quality alert. Version
v-overconfident is producing unsupported answers. Proposed fix: roll back to the last
healthy version. Press 1 to approve. Press 2 to reject."* Press 1, hang up, done. (We
learned the hard way that Twilio trial accounts eat the first three seconds of every
call behind a "press any key" gate — our first three test calls died there. Upgrade the
account before you demo.)

No approval, no action — ever. The brain can do exactly two things, both reversible,
both behind a human decision. If the metric doesn't recover, it says so and escalates
instead of retrying. Restraint is a feature.

`[SCREENSHOT: homeostat-brain's own trace in SigNoz — investigate, await approval, remediate, verify]`

## Did we just trust an LLM to grade an LLM?

Partly — so we measured it instead of assuming. We generated 40 graded answers across
every combination (honest/aggressive prompt × strong/cheap model) and had them labeled
independently, then compared against the judge: agreement on 38 of 40, and the judge
never flagged a good answer as bad — so the alert doesn't cry wolf.

The two misses were the interesting part. Both were answers where every sentence was
true but they answered a *different question* than the one asked (asked about driving a
rental car in Mexico; answered about rental reimbursement). A truthfulness grader can't
see that. Neither can word overlap. "Did you answer the actual question" is a separate
check we haven't built — and we know that precisely because the measurement told us.

Full disclosure: the independent labels came from an AI assistant reading each answer
against the documents, not human annotators. It measures two graders agreeing, not
ground truth. The whole set is in the repo if you want to re-label it.

## The scoreboard

| What | Measured |
|---|---|
| Alert fired at | ratio 0.80 (threshold 0.85, 10-min window) |
| Unattended incident, 03:33 AM | fired at 0.75, self-healed, resolved in 12 min |
| Alert → verified recovery (drill) | 2 min 49 s |
| Judge calls saved by the cheap check | ~73% |
| Judge vs independent labels | 38/40, zero false alarms |
| Load test | 100 claims, 3.2 min, 0 errors, zero new metric series |

## Advice to my past self

1. Put a quality score on every LLM response, attached to the trace. Even a crude one.
   You cannot debug what you cannot see.
2. Alert on a windowed ratio with a target, never on single scores.
3. Timeout every LLM call. The default is infinite. Yes, really.
4. "The process is alive" is not health. "It recently finished real work" is health.
5. If an LLM judge guards your pager, measure it against independent labels first.

If you run agents in production and this made you want to see your own bot's first
lying trace — try it, and tell me what you find. I genuinely want to know how many
green dashboards are lying right now.

*Disclosures: we prototyped the score-on-the-trace idea in our warm-up entry for this
event; this repo is a fresh build with no code copied from it. An AI coding assistant
did a lot of the building and ran the overnight tests; the design decisions and reviews
are ours. Calibration labels are AI-produced, as stated above.*
