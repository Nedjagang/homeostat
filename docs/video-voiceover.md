# Video voiceover — word for word (~2:55 spoken)

Record narration over the clips, or speak live while capturing. Bold = hit the word.
Slashes = tiny pause. Don't perform — report, like you're showing a colleague.

---

**CLIP 1 — the green dashboard (15s)**

> This is an AI insurance agent answering customer questions. / Latency — fine.
> Tokens — fine. Errors — **zero**. Every dashboard says healthy.
> Here's the problem: / it's about to start **lying**, and none of these charts
> will move.

**CLIP 2 — the flip, on the terminal (10s)**

> One bad release. A looser prompt, and a cheaper model — the kind of change that
> ships on a Friday. / Watch what happens.

**CLIP 3 — the lying trace (30s)**

> Within minutes, SigNoz has it. / Every answer gets graded against the documents the
> agent actually retrieved — a three-tier funnel, so the expensive LLM judge only sees
> **suspicious** answers. / The verdict lands on the exact trace, using the standard
> OpenTelemetry gen-ai attributes. / Here's one: the customer asked about earthquake
> damage. The policy says **nothing** about earthquakes. The agent invented an
> exclusion — / and there's the judge's reason, score **zero point one**, attached to
> the request that produced it.

**CLIP 1.5 — architecture diagram (25s)**

> The stack, quickly. / A LangChain agent with RAG, auto-instrumented by OpenLIT,
> exporting OpenTelemetry to self-hosted SigNoz — the Foundry casting file is in the
> repo. / Faithfulness becomes a real SLO: **ninety-eight percent** of answers
> grounded, with a burn-rate alert — because single scores are noisy, windows aren't.
> / And when that alert fires, it doesn't just page someone. It wakes up **the brain**.

**CLIP 4 — the alert fires (15s)**

> Ten minutes in, the error budget is burning seven times too fast — the SLO alert
> **fires**. / Flip back to the traditional dashboard: / still green. Still lying.

**CLIP 5 — the Slack report (25s)**

> The brain investigated through the SigNoz **MCP server** — same four questions every
> time, no free-thinking AI guessing at root causes. / Look at the evidence: the new
> version scoring zero point seven-four. The model changed **with** it. Latency and
> errors never moved. / And the rollback target — **v2 concise** — nobody hardcoded
> that. It found the last healthy version / **in the telemetry**.

**CLIP 6 — the phone rings (20s)**

> And if nobody's watching Slack? / *(let the phone ring, answer on speaker,
> let the voice read the incident aloud)* / …I press **one**. That's the approval.

**CLIP 7 — the thread updates (10s)**

> Phone decision: approved. / The rollback applies — prompt **and** model,
> one reversible action.

**CLIP 8 — the recovery curve (15s)**

> Now the brain verifies its own fix — against the **same metric** that fired.
> / Point-eight… point-eight-five… **recovered**. / Alert to verified recovery:
> **two minutes, forty-nine seconds**.

**CLIP 9 — the brain's own trace (12s)**

> One more thing — the healer is observable too. Investigate, approval, remediate,
> verify — / the whole loop is a trace in the **same SigNoz**.

**CLIP 10 — learnings, over the recovered dashboard (20s)**

> Three things this project taught us. / Strong models **resist** bad prompts — real
> regressions ship as releases. / LLM clients have **no default timeout** — one dead
> socket froze us for hours while "alive" stayed green. / And score every answer on
> the trace — because you can't debug / what you can't **see**. / Everything's in the
> repo — including the incident this system healed at 3:33 AM while we slept.

---

## Timing check
15+10+30+25+15+25+20+10+15+12+20 = **197s ≈ 2:55 spoken** — leaves ~5s of breathing
room. If you're over 3:00 in the edit, cut Clip 9 first (it's the most sacrificeable).

## Delivery notes
- One clip = one take. Don't chase perfection across the whole thing.
- Read each line aloud twice before recording it — the second read is always better.
- Numbers are your emphasis: zero, 0.74, seven times, 2:49, 3:33. Land on them.
- The phone clip needs **no narration during the call** — the robot voice + your
  keypress IS the moment. Silence sells it.
