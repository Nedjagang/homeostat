# Submission pack — Agents of SigNoz form (forms.gle/oJ898STFgpWbeQyq5)

Ready-to-paste answers for every field. One team member submits. Fill the `⬜` items
before sending.

| # | Field | Answer |
|---|---|---|
| 1 | Email | ⬜ your email |
| 2 | Team name | BunkBros |
| 3 | Submitter | ⬜ Praneeth V P (or whoever submits) |
| 4 | Track | **Track 1 (AI & Agent Observability)** |
| 5 | Project description | paste block A below |
| 6 | GitHub link | https://github.com/Nedjagang/homeostat  *(casting.yaml + casting.yaml.lock: ✅ committed — the form explicitly checks this)* |
| 7 | Deployed link (optional) | leave blank — our SigNoz lives on an internal company domain judges can't reach; the repo import script recreates everything on any instance |
| 8 | YouTube video | ⬜ record + upload (unlisted is fine) — **must cover all five: overview, tech stack, architecture, demo, learnings** — script in `docs/demo-script.md` is annotated per element |
| 9 | How we used SigNoz | paste block B below |
| 10 | Blog link | ⬜ publish `docs/blog-draft.md` (Dev.to/Medium) — form says it must be a NEW blog; ours is |
| 11 | Hackathon experience | paste block C below (personalize!) |

---

## Block A — Project description

Homeostat makes an AI agent's truthfulness a first-class golden signal in SigNoz — and
then closes the loop by healing quality regressions with human approval.

ClaimPilot, an insurance-claims agent (LangChain + RAG over policy documents), answers
customer questions. The problem we target: an LLM agent can give confident, wrong
answers while latency, errors, and cost all stay green — the main failure mode of LLM
apps is invisible to traditional monitoring. Homeostat scores every answer for
groundedness through a three-tier eval funnel (deterministic check → lexical-overlap
proxy → LLM judge, gated so only suspicious answers pay for a judge call), attaches the
verdict to the exact trace using the OpenTelemetry GenAI semantic conventions, and
aggregates it into an SLI with an explicit SLO (98% grounded) and a burn-rate alert.

When the alert fires, a "brain" service investigates through the SigNoz MCP server with
a fixed, bounded playbook (score by prompt version and by model, incident window vs
baseline, traditional-signals check), posts an evidence-linked report to Slack with
Approve/Reject buttons, escalates to a phone call (Twilio, keypress approval) if nobody
responds, applies one of two allowlisted reversible actions, verifies recovery against
the same SLI that fired, and saves the incident as a regression test. The healer traces
itself into the same SigNoz.

Everything is verified with recorded evidence: the alert fired and resolved live
(including one fully unattended fire→heal→resolve cycle at 3:33 AM), a human-approved
drill went alert→verified-recovery in 2m49s, the judge is calibrated against
independent labels (38/40 agreement, zero false alarms), and a volume replay proved
bounded metric cardinality (100 claims, zero new series).

## Block B — How we used SigNoz

- **Traces:** every claim is one trace — prompts, retrieved chunks, tool calls, tokens
  (OpenLIT auto-instrumentation), plus our eval verdict as spec-exact
  `gen_ai.evaluation.*` span attributes. The money-shot workflow is filtering spans
  where `gen_ai.evaluation.score.value < 0.5` and opening the exact lying answer.
- **Logs:** every verdict is also a `gen_ai.evaluation.result` log event; WARN
  "unsupported answer" logs carry the trace_id for log→span pivots.
- **Metrics + Dashboards:** bounded-label metrics (score histogram, verdict counter,
  judge tokens, claim outcomes) feed two dashboards built on the new **Dashboards V2
  (Perses v6) API**: "Agent Quality" (turns red when the agent lies) and "Traditional
  Signals" (deliberately stays green through the same regression).
- **Alerts:** faithfulness as an SLO — 98%-grounded target, 7.5× burn-rate rule +
  absolute floor, evaluated over 10-minute windows; fires a webhook to our healing
  service through a SigNoz notification channel (delivery verified container-to-container).
- **SigNoz MCP server:** the brain's entire investigation runs over the MCP endpoint —
  bounded queries only — and we built/validated dashboards, alerts, and calibration
  queries through the MCP + the official SigNoz agent skills during development.
- **Foundry:** casting.yaml + casting.yaml.lock committed; `signoz/push-packs.py`
  recreates the full dashboard/alert pack on any fresh instance idempotently.

## Block C — Hackathon experience (personalize this!)

The best parts were the failures. We flipped our chaos switch expecting the agent to
start lying and the model simply refused — it kept being honest despite a prompt
ordering it not to be, which taught us that real regressions ship as releases (prompt +
cheaper model together), not as evil prompts. An overnight run froze with the health
flag still green and our own telemetry diagnosed it: a laptop suspend, a dead socket,
and an LLM client with no default timeout — the exporter crashing on a minus-7,885-second
timeout was the clue. And SigNoz caught and healed an incident at 3:33 AM while the
whole team slept, which is the moment the project stopped feeling like a demo. We
shipped four honest postmortems in the repo, and we'd do this hackathon again just for
what the failures taught us.

---

## Pre-submission checklist

- [x] Repo public, casting.yaml + casting.yaml.lock committed (form checks this)
- [x] Disclosures in README + blog (prior warm-up work, AI assistance)
- [ ] VM control-token fix (security — do first)
- [ ] Screenshots into the blog (markers in docs/blog-draft.md)
- [ ] Blog published (NEW post — form says previous blogs are ineligible)
- [ ] Video ≤3 min on YouTube covering ALL FIVE: overview, tech stack, architecture,
      demo, learnings (script: docs/demo-script.md)
- [ ] Optional but strong: Foundry clean-host run to back the casting files
- [ ] Submit the form (one member), a day before the deadline
