# 3-minute demo script — exact commands, shot by shot

Everything below is real and tested; nothing is mocked. Prep and fallbacks at the end.

**The submission form requires the video to cover five elements — mapped here:**
overview (Shot 1), architecture + tech stack (Shot 1.5), demo (Shots 2–7),
learning outcomes (Shot 8). Don't cut 1.5 or 8.

**Cast:** ClaimPilot service (`:8091`), brain (`:8090`), SigNoz at
`https://signoz.apteancloud.dev`, Slack `#all-bunkbros-signoz-alerts`.

**Pre-roll (before recording):** service running at demo pace, brain running
(NO auto-approve), bot invited to the channel, both dashboards open in tabs:

```powershell
$env:CLAIM_INTERVAL_SECONDS = "5"        # demo density
# tab 1 — Traditional:   https://signoz.apteancloud.dev/dashboard/019f95ac-ebb0-7a75-bfd2-7e633f559c76
# tab 2 — Agent Quality: https://signoz.apteancloud.dev/dashboard/019f95ac-d454-751d-adfb-1fac5d3dc7b1
# tab 3 — Alerts list:   https://signoz.apteancloud.dev/alerts
```

## Shot 1 — the green lie (~20s)
Traditional dashboard, last 30 min: latency flat, tokens flat, error rate zero.
> "Latency fine, cost fine, zero errors. By everything we monitor, this insurance agent
> is healthy. Now watch it lie."

## Shot 1.5 — architecture + tech stack in one breath (~20s)
One slide/diagram (the ASCII from the README rendered nicely):
> "The stack: a LangChain claims agent with RAG, auto-instrumented by OpenLIT, exporting
> OpenTelemetry to self-hosted SigNoz — installed via Foundry, casting file in the repo.
> Every answer is scored by a three-tier eval funnel and the verdict lands on the trace.
> SigNoz alerts on it as an SLO, and a small Python 'brain' service investigates over
> the SigNoz MCP server and heals with human approval via Slack or a phone call."

## Shot 2 — inject the regression (~15s)
Terminal, on camera:
```bash
curl -X POST -H "Authorization: Bearer $CLAIMPILOT_CONTROL_TOKEN" \
  "http://localhost:8091/control/chaos/prompt_overconfident?enabled=true"
```
> "One bad release: a looser prompt and a cheaper model — the kind of change that ships
> on a Friday."

## Shot 3 — the money shot: catch the exact lie (~40s)
Agent Quality dashboard: SLI curve bending down, *Faithfulness by prompt version*
splitting — `v_overconfident` sinking while others hold.
Then Traces Explorer → filter `gen_ai.evaluation.score.value < 0.5` → open a span:
the customer question, the retrieved policy clauses, the confident wrong answer, the
judge's one-line reason — all on one trace. Pivot: Logs → WARN `unsupported answer` →
click the trace_id → same span.
> "Every answer carries its own verdict, attached to the exact request. This span is the
> agent inventing a policy determination — and here's the judge explaining why it's wrong."

## Shot 4 — the SLO fires (~20s)
Alerts tab: **Faithfulness SLO fast burn — claimpilot** goes firing (~6–10 min after
injection at demo pace; pre-stage by injecting before recording if tight).
Flip briefly back to Traditional: still green.
> "Faithfulness is an SLO here — 98% grounded, burn-rate alert. It just fired.
> Traditional signals never moved."

## Shot 5 — the brain investigates (~30s)
Slack: the homeostat report arrives (fired by the alert webhook; for a laptop demo:
`curl -X POST http://localhost:8090/simulate`). Read the evidence bullets on camera:
offending version, the model that changed with it, "traditional signals stayed green",
the revert target. Click "open in SigNoz".
> "The brain investigated over the SigNoz MCP with a bounded playbook — every claim in
> this report is a number it queried, not a guess."

## Shot 6 — approve, heal, verify (~40s)
Click **Approve heal** in Slack. Watch the thread:
applied `pin_prompt_version(v1_grounded)` → "verifying…" → (time-lapse or pre-staged)
"✅ verified: grounded ratio recovered". Show Agent Quality climbing back, and
`chaos/regressions/` gaining a JSON case.
> "Reversible action, human-approved, verified against the same SLI that fired — and the
> incident just became a regression test."

## Shot 7 — the healer is observable too (~15s)
Traces Explorer → service `homeostat-brain`: the incident trace with investigate /
await_approval / remediate / verify spans, `homeostat.action` attributes.
> "The whole loop lives in SigNoz — including the thing doing the healing."

## Shot 8 — learnings (~15s, talking head or text over the recovered dashboard)
> "Three things we learned: strong models resist bad prompts — real regressions ship as
> releases, prompt and model together. LLM clients have no default timeout — one dead
> socket froze our loop for hours while 'alive' stayed green. And judge scores are noisy
> per-answer — alert on windowed ratios, never single scores. All four postmortems are
> in the repo."

## Pacing & fallbacks
- The slow segments are alert-fire (~6–10 min) and recovery (~10 min). Record them as
  time-lapse or pre-stage a second injected environment that's already mid-incident.
- Screenshot every shot in advance; if anything stalls live, cut to stills.
- If Slack misbehaves: `BRAIN_AUTO_APPROVE=1` exists, but shows as auto-approved —
  prefer the real click on camera.
