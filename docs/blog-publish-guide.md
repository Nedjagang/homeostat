# Blog publish guide — screenshots pre-located, then publish

The draft is `docs/blog-draft.md`. It has **five** `[SCREENSHOT]` markers. Every shot
below is pre-located with the exact UI path and time window (UTC and IST) — click,
don't hunt. All of it is real recorded history; nothing needs to be re-staged.

## The five screenshots

**S1 — the green dashboard next to the made-up answer** *(opening shot)*
- Tab A: `https://signoz.apteancloud.dev/dashboard/019f95ac-ebb0-7a75-bfd2-7e633f559c76`
  (Traditional Signals), time range **Jul 25 19:30 → 20:30 UTC** (Jul 26, 01:00–02:00
  IST). Everything flat and green.
- Tab B: the lying trace (see S2). Compose side-by-side or take two shots.

**S2 — the lying trace, open**
- Direct link: `https://signoz.apteancloud.dev/trace/a8061adfcebb6bf04f46ae020fcb5eca`
  (claim at **Jul 25 20:07 UTC** / Jul 26 01:37 IST, score < 0.5).
- Click the `claim.process` root span → attributes panel: show
  `gen_ai.evaluation.score.value`, `gen_ai.evaluation.explanation`, `prompt.version`,
  `gen_ai.request.model`. Expand a child LLM span to show the prompt/answer text.
- Backups if that one isn't photogenic: `190869a53744ae6c5f7504dccdf949ab` (19:46 UTC),
  `a734baa0421dcb2e73b117a02c38630d` (19:42 UTC), `fda7b298ac29a310fcdb4c738e32c6f7`
  (19:03 UTC). Or filter Traces Explorer: service `claimpilot`, span name
  `claim.process`, `gen_ai.evaluation.score.value < 0.5`, last 2 days.

**S3 — alert history: the 3:33 AM unattended save**
- Alerts → **Faithfulness SLO fast burn — claimpilot** → History tab.
- Time range **Jul 24 03:00 → 04:00 UTC** (Jul 24, 08:30–09:30 IST).
- Shows: firing at 03:33 with value 0.75, resolved 03:45. If the UI shows the full
  history list, widen to Jul 23–25 to capture several fire/resolve pairs in one shot.

**S4 — the Slack report with the Approve button**
- Slack `#all-bunkbros-signoz-alerts`, scroll to **Jul 25, ~11:24 AM IST** (05:54 UTC).
- The homeostat report with evidence bullets, and just after it, the "approved by
  praneeth.vedalaveni" update + the recovery thread ("✅ verified: grounded ratio
  recovered to 0.95"). One tall screenshot catches the whole story.

**S5 — the healer's own trace**
- Traces Explorer → service `homeostat-brain`, time range **Jul 25 05:50 → 06:10 UTC**
  (11:20–11:40 IST).
- Open the `brain.incident` trace: investigate → await_approval → remediate → verify
  spans visible in the waterfall, `homeostat.action` in attributes.

Optional extras if you want more visuals: the recovery curve (Agent Quality dashboard,
Jul 25 05:30–06:30 UTC — the 0.80→0.95 climb) and the verdicts-by-tier pie showing the
funnel economics (last 24 h).

## Publish steps

1. Drop the screenshots into the draft at the markers; delete the `> DRAFT NOTE` block.
2. **Voice pass (the important one):** read it aloud once. Any sentence you wouldn't
   say out loud — rewrite it in your words. Add one detail only you know (what you were
   doing when you clicked Approve, what the phone call sounded like). The draft is a
   skeleton of true events; the voice should be yours.
3. Byline: it's a team entry — add "Team BunkBros: <names>" under the title or in the
   footer, and keep the disclosure paragraph exactly as written (prior warm-up work +
   AI assistance — the honesty is a feature, not a risk).
4. Platform: Medium or Dev.to both satisfy the form (it just wants a link). Tags:
   `SigNoz`, `OpenTelemetry`, `LLM`, `Observability`, `SRE`.
5. Cover image: S1 (the green dashboard beside the lie) is the thesis in one picture.
6. Before hitting publish, check: repo link works, every number matches the table,
   every screenshot has a sentence referencing it, DRAFT NOTE gone.
7. Paste the published URL into the submission form (field 10) and into
   `docs/submission-pack.md`.

## Timezone cheat sheet (IST = UTC + 5:30)

| Event | UTC | IST |
|---|---|---|
| First alert fire (0.80) | Jul 23, 22:25 | Jul 24, 03:55 |
| Unattended save (0.75) | Jul 24, 03:33–03:45 | Jul 24, 09:03–09:15 |
| Human-approved drill | Jul 25, 05:54–06:05 | Jul 25, 11:24–11:35 |
| Fresh lying trace (S2) | Jul 25, 20:07 | Jul 26, 01:37 |
