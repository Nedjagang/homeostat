# Video production — the complete single-doc guide

One live incident, filmed as ten short clips, assembled to 3:00. Nothing mocked.

**Roles:**
- **You** — run the recorder, click, speak, answer the phone.
- **Claude (chat, off-screen)** — watches the telemetry from outside, drives timing,
  and posts a message the moment each clip becomes filmable ("alert just fired —
  record the Alerts tab NOW"). If the incident drags, Claude densifies traffic from
  the laptop (see Fallbacks).

**Terminals — there are TWO, don't mix them:**
- **Terminal A (ON camera):** a plain PowerShell window, font bumped to 16pt+. Only
  two commands ever run here (below). No secrets visible — the token lives in
  `$env:TOKEN`.
- **Claude Code chat (OFF camera):** second monitor or behind the recorder. Never in
  the recording.

---

## 1. Pre-flight (verified state + what's left)

Already verified ✅: control auth ON (401 without token) · alert→brain webhook
delivery · Slack listener connected · phone-leg env complete (trial account — expect
the "press any key" gate) · chaos scheduler stopped · claim loop healthy and grounded.

Do before rolling:
- [ ] Recorder: OBS or Win+G, 1080p, **system audio ON** (Slack ping + phone speaker).
- [ ] Browser: hide bookmarks bar, close personal tabs. Six tabs in this order:
      ① Traditional dashboard → `https://signoz.apteancloud.dev/dashboard/019f95ac-ebb0-7a75-bfd2-7e633f559c76`
      ② Agent Quality dashboard → `https://signoz.apteancloud.dev/dashboard/019f95ac-d454-751d-adfb-1fac5d3dc7b1`
      ③ Alerts list → `https://signoz.apteancloud.dev/alerts`
      ④ Traces Explorer (pre-set filter: service `claimpilot`, span `claim.process`,
         `gen_ai.evaluation.score.value < 0.5`, last 30 min)
      ⑤ Slack `#all-bunkbros-signoz-alerts`
      ⑥ Terminal A
- [ ] Terminal A setup (run before recording):
      ```powershell
      $env:TOKEN = "<your VM control token>"    # never echo it
      ```
- [ ] Phone on the desk, speaker mode ready.
- [ ] Dashboards ① and ② set to "Last 30 minutes".
- [ ] Tell Claude **ROLL**.

## 2. The only on-camera commands (Terminal A)

**Clip 2 — inject the bad release:**
```powershell
curl.exe -X POST -H "Authorization: Bearer $env:TOKEN" "https://signoz.apteancloud.dev/homeostat/control/chaos/prompt_overconfident?enabled=true"
```

**Optional b-roll — show live state (read-only, no auth needed):**
```powershell
curl.exe -s "https://signoz.apteancloud.dev/homeostat/control/state"
```

That's it. Everything else in the video is UI, Slack, and the phone. The heal itself
is performed by the brain after your keypress — no command needed.

## 3. Shot list with narration (say the bold-marked words with weight)

**CLIP 1 · T−2m · Tab ① Traditional dashboard · 15s**
Claude confirms baseline is green first.
> "This is an AI insurance agent answering customer questions. / Latency — fine.
> Tokens — fine. Errors — **zero**. Every dashboard says healthy. Here's the problem:
> / it's about to start **lying**, and none of these charts will move."

**CLIP 2 · T+0 · Terminal A · 10s** — run the flip command on camera.
> "One bad release. A looser prompt, and a cheaper model — the kind of change that
> ships on a Friday. / Watch what happens."

**CLIP 1.5 · T+3m (dead time) · architecture diagram (README or a slide) · 25s**
> "The stack, quickly. / A LangChain agent with RAG, auto-instrumented by OpenLIT,
> exporting OpenTelemetry to self-hosted SigNoz — the Foundry casting file is in the
> repo. / Faithfulness becomes a real SLO: **ninety-eight percent** of answers
> grounded, with a burn-rate alert — because single scores are noisy, windows aren't.
> / And when that alert fires, it doesn't just page someone. It wakes up **the brain**."

**CLIP 3 · T+4–6m · Tab ④ Traces (Claude calls when lying spans exist) · 30s**
Refresh, open a fresh red span, expand attributes.
> "Within minutes, SigNoz has it. / Every answer gets graded against the documents the
> agent actually retrieved — a three-tier funnel, so the expensive LLM judge only sees
> **suspicious** answers. / The verdict lands on the exact trace, using the standard
> OpenTelemetry gen-ai attributes. / Here's one: the customer asked about earthquake
> damage. The policy says **nothing** about earthquakes. The agent invented an
> exclusion — / and there's the judge's reason, score **zero point one**, attached to
> the request that produced it."

**CLIP 4 · T+~10–14m · Tab ③ Alerts (Claude calls the fire) · 15s**
Show the firing rule, then flip to Tab ① for two seconds.
> "Ten minutes in, the error budget is burning seven times too fast — the SLO alert
> **fires**. / Flip back to the traditional dashboard: / still green. Still lying."

**CLIP 5 · +30s after fire · Tab ⑤ Slack · 25s** — the report arrives. DON'T click.
> "The brain investigated through the SigNoz **MCP server** — same four questions
> every time, no free-thinking AI guessing at root causes. / Look at the evidence:
> the new version scoring zero point seven-four. The model changed **with** it.
> Latency and errors never moved. / And the rollback target — **v2 concise** —
> nobody hardcoded that. It found the last healthy version / **in the telemetry**."

**CLIP 6 · +3m of not clicking · THE PHONE · 20s**
Film the phone (second phone camera, or speaker audio into the screen recording).
Trial account: when you answer, **press any key at Twilio's gate first**, then the
incident readout plays, then **press 1**. Say only, before it rings:
> "And if nobody's watching Slack?"
Then let the call speak. After pressing 1, nothing — silence sells it.

**CLIP 7 · +10s · Tab ⑤ Slack thread · 10s**
> "Phone decision: approved. / The rollback applies — prompt **and** model, one
> reversible action."

**CLIP 8 · +5–10m (Claude calls recovery) · Tab ② Agent Quality · 15s**
> "Now the brain verifies its own fix — against the **same metric** that fired. /
> Point-eight… point-eight-five… **recovered**. / Alert to verified recovery:
> **two minutes, forty-nine seconds**."

**CLIP 9 · any time after · Tab ④ Traces, service `homeostat-brain` · 12s**
> "One more thing — the healer is observable too. Investigate, approval, remediate,
> verify — / the whole loop is a trace in the **same SigNoz**."

**CLIP 10 · any time · recovered dashboard b-roll · 20s**
> "Three things this project taught us. / Strong models **resist** bad prompts — real
> regressions ship as releases. / LLM clients have **no default timeout** — one dead
> socket froze us for hours while 'alive' stayed green. / And score every answer on
> the trace — because you can't debug / what you can't **see**. / Everything's in the
> repo — including the incident this system healed at 3:33 AM while we slept."

## 4. What Claude does, exactly

| When | Claude's action (off-screen) |
|---|---|
| ROLL | Verify baseline fresh + green via `/state` and metrics; give GO for Clip 1 |
| T+0 | Confirm the flip landed (flags in `/state`) |
| T+2→6 | Poll for unsupported verdicts; post "CLIP 3 ready" with count |
| T+6→14 | Watch the rule via the SigNoz API; post "ALERT FIRED — CLIP 4 now" |
| after fire | Confirm webhook hit the brain; post "report should be in Slack — CLIP 5" |
| Slack window | Countdown the 3-minute timeout; post "phone imminent — camera on it" |
| after keypress | Watch the SLI recover; post the exact moment for CLIP 8 |
| wrap | Confirm heal state, flip anything residual back to grounded, re-verify baseline |

## 5. Assembly & upload

Order: 1 → 2 → 3 → 1.5 → 4 → 5 → 6 → 7 → 8 → 9 → 10 (≈2:55; cut Clip 9 first if over).
Any editor works (Clipchamp is preinstalled on Windows 11). Trim dead frames, keep the
phone audio raw. Upload to YouTube (unlisted is fine) → title: *"Homeostat — SigNoz
catches an AI agent lying and heals it (Agents of SigNoz, Track 1)"* → paste the URL
into form field 8. The five judged elements map: overview (1), stack + architecture
(1.5), demo (2–9), learnings (10).

## 6. Fallbacks

- **Alert slow?** Claude launches extra claim traffic from the laptop (loadgen with
  the chaos env set) to densify the window. Alternatively wait — the next 10-min
  window catches it.
- **Phone misbehaves?** Click **Approve** in Slack on camera (still a great clip) and
  film the phone separately afterwards: Claude triggers `python brain/voice.py test`
  from the laptop, you film answering it.
- **A clip flubbed?** Re-record just that clip. Chaos can be re-flipped for a second
  incident — the system doesn't care, and every incident is real.
- **Anything stalls mid-take:** keep recording. Honest waiting beats a staged cut.
