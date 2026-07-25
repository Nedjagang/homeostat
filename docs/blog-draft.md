# Our AI agent gave a customer a wrong answer. Every dashboard was green.

*Team BunkBros — Agents of SigNoz hackathon. Code:
[github.com/Nedjagang/homeostat](https://github.com/Nedjagang/homeostat).*

> DRAFT NOTE (delete before publishing): add a real screenshot wherever you see
> `[SCREENSHOT]`. Don't publish a claim without its picture.

We built an insurance claims bot. You ask it "is my burst pipe covered?" and it looks
up the policy documents and answers.

One day it told a customer that earthquake damage was "specifically excluded" by their
policy. Sounds reasonable. Except the policy says nothing about earthquakes. The bot
made it up.

Here is what our monitoring said while that happened:

- Response time: normal.
- Token cost: normal.
- Errors: zero.

`[SCREENSHOT: the green dashboard next to the made-up answer]`

That's the problem. Latency, errors, cost — all of it measures whether the bot
*answered*. None of it measures whether the answer was *true*. For an LLM app, wrong
answers are the main failure mode, and they are invisible on a normal dashboard.

So we spent the hackathon making SigNoz treat truthfulness the way SREs treat uptime.
Score it on every request. Put the score on the trace. Alert when it drops. Then go one
step further: when the alert fires, investigate it and fix it, with a human clicking
approve.

## Step 1: score every answer

After the bot answers, we grade the answer against the documents it actually retrieved.
Three checks, in order of cost:

1. **Free check.** Did the bot answer even though it retrieved *nothing*? If yes, the
   answer is made up by definition. Score 0, done. Costs nothing.
2. **Cheap check.** How many words does the answer share with the retrieved documents?
   Real answers quote the policy ("$500 deductible, Section 2"). Made-up answers don't,
   because there is nothing to quote. High overlap = pass, skip the expensive check.
3. **Expensive check.** A second LLM call reads the question, the retrieved documents,
   and the answer, and returns a score from 0 to 1 with a one-line reason. This only
   runs on answers the cheap check found suspicious, plus a 2% random sample to make
   sure the cheap check itself isn't lying to us.

In our runs, the cheap check cleared about 3 out of 4 answers. So the judge bill drops
to roughly a quarter of "judge everything", and the alert still works (we tested that —
more below).

The score lands in three places in SigNoz:

- On the **trace**, so you can open the exact request and see the question, the
  documents, the answer, and why it failed. We used the OpenTelemetry GenAI attribute
  names (`gen_ai.evaluation.score.value` and friends) so this isn't a homemade format.
- As a **log event**, so you can pivot from a "bad answer" log line to the trace.
- As a **metric**, so you can chart it and alert on it. Metric labels are only
  low-cardinality things like the prompt version. Trace IDs and reasons stay on traces
  and logs, where high cardinality belongs.

`[SCREENSHOT: one bad trace open in SigNoz — question, retrieved docs, answer, judge reason]`

## Step 2: alert on it like an SRE would

We didn't want "alert if score < 0.5", because single scores are noisy. The same claim
scored 0.2 on one run and 0.96 on another — the bot words its answer differently every
time. You'd get paged constantly for nothing.

Instead we set a target, the way you'd set one for availability: **98% of answers in a
window should be grounded** (grounded = the judge scored it 0.5 or above). The alert
fires when a 10-minute window is eating that 2% error budget about 7 times faster than
allowed. In plain terms: fire when roughly 1 in 7 answers is bad, stay quiet when one
noisy score comes through.

Two things we learned tuning this on real traffic:

- Our first window was 5 minutes. At about one claim per minute, that's only 5 or 6
  answers per window, and pure luck kept the ratio above the line during a real
  incident. We doubled the window and it caught everything after that.
- At volume, about 3% of answers score badly even when nothing is wrong (the judge is
  strict, retrieval occasionally misses). That's *why* the target is 98% and not 100%.
  We found that number by running 100 claims and counting, not by guessing.

`[SCREENSHOT: alert history showing fired at 0.80, resolved after the fix]`

## The failure we couldn't create (our favorite bug)

To demo this you need the bot to actually lie on demand. So we added a chaos switch
that swaps the system prompt to an aggressive one: "always give a confident decision,
never say you are unsure."

We flipped it. Nothing happened.

The model (a strong one) simply refused. It kept saying "the policy doesn't address
this", politely ignoring the prompt telling it never to say that. And our judge kept
correctly scoring that honesty as fine. Twenty minutes of injected "chaos" and the
score never moved.

The fix was to make the failure realistic instead of theatrical. Real quality
regressions usually ship as a *release*: someone tweaks the prompt AND swaps in a
cheaper model to save money, in the same change. So our chaos switch now does both.
The cheap model happily invents policy exclusions. And because the model name is on
every trace, the change shows up in telemetry twice — the prompt version changed *and*
the model changed. One rollback undoes both, because that's what reverting a release
means.

## The 3 a.m. failure (the one that humbled us)

We left the whole thing running overnight, unattended, on a laptop. In the morning:
610 failed claims and the processing loop frozen since evening. The health flag said
the loop was alive. It was lying too.

What actually happened, pieced together from our own telemetry in SigNoz:

1. The laptop kept going to sleep (Windows ignores your power settings when the lid
   closes).
2. Every wake-up left dead network connections behind.
3. The OpenAI client library ships with **no request timeout by default**. One call
   blocked forever on a dead connection, and the loop sat there holding it.

The clue that cracked it: our log exporter crashed trying to set a timeout of
**minus 7,885 seconds**. A negative timeout means the clock jumped two hours mid-request
— which is exactly what suspend/resume looks like from inside a process.

Three fixes, all boring, all things we'd tell any SRE to check on any LLM service:

- Set an explicit timeout on every LLM call. Every one.
- Don't trust "the thread is alive" as health. Track "when did we last finish a unit of
  work" instead.
- Keep a local copy of your error logs. Ours went only to the telemetry pipeline, which
  was down for the same reason everything else was. The network can't report on itself.

## Step 3: close the loop

When the alert fires, a small service we call the brain wakes up. It asks SigNoz four
questions, always the same four (it's a fixed checklist, not a free-thinking agent —
we did not want an AI guessing at root causes):

1. What's the average score per prompt version, in the incident window vs the hour
   before?
2. Same question, per model.
3. Did error rate move? Did latency move?
4. Which older version was still healthy?

Then it posts what it found to Slack, with the numbers, and two buttons.

`[SCREENSHOT: the Slack message — evidence lines, Approve heal / Reject buttons]`

Here's the message from our live run, paraphrased: *"Version v_overconfident is
averaging 0.74. Version v1_grounded is at 1.00. The low scores are all on the cheap
model. Error rate and latency didn't move. Proposing: pin back to v2_concise."*

Note the proposed rollback target: **v2_concise**, not the oldest safe prompt. The
brain picked it because our version history showed it was the most recent version that
was actually healthy in the data. Nobody hardcoded that. It read it out of SigNoz.

One of us clicked Approve. The brain called the bot's admin API, pinned the old
version, then watched the same metric the alert fired on. Ten minutes later the ratio
was back above target and it posted "recovered" in the thread. The whole incident, from
alert to verified recovery, also exists as a trace in SigNoz — the fixer is monitored
by the same system as the thing it fixed.

If nobody clicks? It times out and does nothing. If the metric doesn't recover? It
says so and escalates. The brain can only do two things, both reversible, both behind
a human click. That restraint is deliberate.

## Did we just trust an LLM to grade an LLM?

Partly, yes — so we measured how good the grader is instead of assuming. We generated
40 graded answers across all the combinations (honest prompt, aggressive prompt, strong
model, cheap model) and had them labeled independently, then compared labels against
the judge.

Result: agreement on 38 of 40. The judge never flagged a good answer as bad (that
matters — it means the alert doesn't cry wolf). It missed 2 of 7 bad ones, and both
misses were the same trick: an answer where every sentence is true but it answers a
*different question* than the one asked. A truthfulness grader can't see that, and
neither can word overlap. Checking "did you answer the actual question" is a separate
grader we haven't built yet. It's the clearest next step, and we know that because the
measurement told us.

Honesty note: the independent labels came from an AI assistant reading each answer
against the documents, not from human annotators. So this measures two graders
agreeing, not ground truth. It's in the repo (`chaos/calibration/`) if you want to
re-label it yourself.

## The numbers, in one place

| What | Measured |
|---|---|
| Alert fired at | grounded ratio 0.80 (threshold 0.85, 10-min window) |
| Unattended incident at 03:33 | fired at 0.75, self-healed, resolved 12 min later |
| Alert → verified recovery (drill) | 2 min 49 s |
| Judge calls saved by the cheap check | ~73% at healthy baseline |
| Judge vs independent labels | 38/40 agree, no false alarms |
| Load test | 100 claims, 3.2 min, 0 errors, zero new metric series |

## If you run LLMs in production, steal these

1. Put a quality score on every response, attached to the trace. Even a crude one.
   You cannot debug what you cannot see.
2. Alert on a windowed ratio with an explicit target, never on single scores.
3. Timeout every LLM call. The default is infinite.
4. "Process is alive" is not health. "Recently did useful work" is health.
5. If you use an LLM judge, measure it against independent labels before you trust it
   with your pager.

## Disclosures

We prototyped the score-on-the-trace idea in a pre-hackathon warm-up post; this repo is
a fresh build with no code copied from it. An AI coding assistant did a lot of the
building and ran the overnight tests; the design calls and the reviews are ours. The
calibration labels are AI-produced, as stated above.
