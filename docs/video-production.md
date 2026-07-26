# Video — one-shot run. Do this, do that. Nothing else.

Narration lines: `docs/video-voiceover.md`. Slides: `docs/slides.html` (F11, arrows).
Claude calls every moment in chat — keep chat OFF the recorded screen.

## SETUP (5 min)

1. PowerShell (big font): `$env:TOKEN = "<your VM token>"`
2. Open 7 things, this order: slides.html · Traditional dash · Agent Quality dash ·
   Alerts · Traces (filter: `gen_ai.evaluation.score.value < 0.5`, last 30 min) ·
   Slack · the PowerShell
3. Both dashboards → time range "Last 30 minutes"
4. Hide bookmarks bar. Close everything else.
5. Phone on desk, speaker on, volume up.
6. Recorder: 1080p, system audio ON. PAUSE button ready — you'll pause during waits.
7. Type ROLL in chat. Wait for Claude's GO.

## RECORD (pause recorder wherever it says WAIT)

1. Slide 1 (title). Say Clip-1 opening line over it.
2. Traditional dashboard. Say the rest of Clip 1 ("...none of these charts will move").
3. PowerShell. Run, while saying Clip 2 line:
   `curl.exe -X POST -H "Authorization: Bearer $env:TOKEN" "https://signoz.apteancloud.dev/homeostat/control/chaos/prompt_overconfident?enabled=true"`
4. Slide 4 (architecture). Say Clip 1.5 lines.
5. WAIT — pause recorder until Claude posts "CLIP 3 READY" (~4 min).
6. Traces tab. Refresh. Open a red span. Expand attributes. Say Clip 3 lines.
7. WAIT — pause until Claude posts "ALERT FIRED" (~10 min).
8. Alerts tab: show the firing rule. Flip to Traditional dash. Say Clip 4 lines.
9. Slack tab. Report arrives ~30s later. Read evidence on camera. Say Clip 5 lines.
   DO NOT CLICK ANYTHING.
10. WAIT — recorder ON, camera/phone ready. Phone rings 3 min after the report.
11. Answer on speaker. Press ANY KEY at the Twilio gate. Listen. Press 1.
    Say nothing during the call.
12. Slack tab: thread shows "phone decision: approved". Say Clip 7 line.
13. WAIT — pause until Claude posts "RECOVERED" (~5–10 min).
14. Agent Quality dash: the dip and climb. Say Clip 8 lines.
15. Traces tab → service `homeostat-brain` → open incident trace. Say Clip 9 lines.
16. Slides 8 → 9 → 10, arrow through while saying Clip 10 lines.
17. Stop recording.

## IF SOMETHING BREAKS

- Phone doesn't ring → click Approve in Slack on camera, keep going. Film phone later.
- Flubbed a line → say it again immediately, cut the bad take in edit.
- Anything else → check chat; Claude is watching everything.

## AFTER

1. Trim the pauses/flubs. Target ≤ 3:00. Cut step 15 first if over.
2. Upload to YouTube (unlisted). Title: "Homeostat — SigNoz catches an AI agent lying and heals it".
3. URL → form field 8.
