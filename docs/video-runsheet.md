# Video run sheet — one live incident, filmed

Strategy: record SHORT CLIPS of each real moment as the incident unfolds (I drive the
chaos and timing; you record and click), then assemble to 3:00 with voiceover from
`docs/demo-script.md`. Nothing staged, nothing mocked.

## Pre-flight (15 min, before anything rolls)

- [ ] **VM token fix applied** (CLAIMPILOT_CONTROL_TOKEN set + containers recreated) —
      security, and the on-camera curl must show `-H "Authorization: Bearer $TOKEN"`,
      never the raw value. Set `$env:TOKEN` in your terminal beforehand.
- [ ] **Twilio decision:** upgraded account = clean call ("This is Homeostat…" →
      press 1). Trial = the call opens with Twilio's "press any key" gate — works, but
      film the upgraded version if possible; it's the money shot.
- [ ] Recorder: OBS or Xbox Game Bar (Win+G), 1080p, system audio ON (for the Slack
      ping). Hide bookmarks bar; close personal tabs; don't show `.env` files.
- [ ] Phone on the desk, camera-ready (film it with a second phone, or answer on
      speaker so the screen recording catches the audio).
- [ ] Tabs, in order: ① Traditional dashboard ② Agent Quality dashboard ③ Alerts list
      ④ Traces Explorer ⑤ Slack ⑥ terminal.
- [ ] Say **ROLL** to me — I confirm the system is healthy-baseline and standing by.

## The live sequence (~35 min of waiting, ~6 min of actual footage)

| T | What happens | You record (clip) |
|---|---|---|
| T−2m | Baseline healthy | **Clip 1 (20s):** Traditional dashboard, last 30m — flat, green. "By everything we monitor, this agent is healthy." |
| T+0 | **You run the flip on camera:** `curl -X POST -H "Authorization: Bearer $env:TOKEN" "https://signoz.apteancloud.dev/homeostat/control/chaos/prompt_overconfident?enabled=true"` | **Clip 2 (15s):** the terminal command + JSON response |
| T+2→6 | Lying answers start landing | **Clip 3 (30s):** Traces Explorer, filter `gen_ai.evaluation.score.value < 0.5`, open a fresh span: question → retrieved docs → fabricated answer → judge reason |
| T+3 | (dead time) | **Clip 1.5 (20s):** the architecture diagram — record the slide/README while narrating stack + architecture (required by the form) |
| T+8→12 | **Alert fires** (I'll call it the moment I see it) | **Clip 4 (20s):** Alerts page — "Faithfulness SLO fast burn" firing; flip to Traditional tab: still green |
| +30s | Webhook → brain → **Slack report arrives** | **Clip 5 (25s):** the report — read the evidence bullets aloud; DON'T click |
| +3m | Slack window times out → **your phone rings** | **Clip 6 (30s):** the phone — answer on speaker, the voice reads the incident, **press 1** (trial account: press any key first) |
| +10s | Thread updates: "📞 phone decision: approved" → "applied pin… verifying" | **Clip 7 (15s):** the Slack thread updating |
| +5→10m | SLI recovers, "✅ verified… recovered" posts | **Clip 8 (20s):** Agent Quality dashboard — the dip and the climb back; the recovery message |
| after | The healer's own telemetry | **Clip 9 (15s):** Traces → service `homeostat-brain` → the incident trace: investigate → await_approval → remediate → verify |
| any | Closing | **Clip 10 (15s):** talking head or dashboard b-roll — the three learnings (script Shot 8) |

## Assembly (target 3:00)

Order: 1 → 2 → 3 → **1.5** → 4 → 5 → 6 → 7 → 8 → 9 → **10**.
That covers the form's five required elements: overview (1), tech stack + architecture
(1.5), demo (2–9), learnings (10). Trim the waits; cut on action. Upload to YouTube
(unlisted is fine) → URL into form field 8.

## Fallbacks

- Alert slow to fire? I can densify the claim rate live. Worst case we re-record Clip 4
  on the next scheduler cycle — the system produces incidents every 3 hours anyway.
- Phone misbehaves? Click Approve in Slack on camera instead — still a great shot —
  and film the phone leg separately with `python brain/voice.py test`.
- Anything stalls mid-take: keep recording; honest waiting beats a staged cut.
