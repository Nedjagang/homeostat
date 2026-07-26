# Submission pack — paste-ready answers

Fill the `⬜` bits, paste the rest.

| # | Field | Answer |
|---|---|---|
| 1 | Email | ⬜ |
| 2 | Team name | BunkBros |
| 3 | Submitter | ⬜ Praneeth |
| 4 | Track | Track 1 (AI & Agent Observability) |
| 5 | Project description | Block A |
| 6 | GitHub | https://github.com/Nedjagang/homeostat |
| 7 | Deployed link | leave blank (SigNoz is on an internal domain; the repo recreates it anywhere) |
| 8 | YouTube video | ⬜ paste link |
| 9 | How we used SigNoz | Block B |
| 10 | Blog link | ⬜ paste link |
| 11 | Experience | Block C |

---

## Block A — Project description

We built an insurance claims bot, then asked an uncomfortable question: if it starts
confidently making things up, would our monitoring even notice? It wouldn't — latency,
errors, and cost all stay green while the answer is a lie.

Homeostat fixes that. It grades every answer against the documents the bot actually
retrieved, using a funnel of cheap-to-expensive checks so an LLM judge only sees the
suspicious ones. The verdict lands on the exact trace in SigNoz, and faithfulness
becomes a real SLO — 98% grounded, with a burn-rate alert.

When that alert fires, a small "brain" service investigates through the SigNoz MCP
server, posts the evidence to Slack, and — if nobody clicks — calls the on-call phone
and takes the fix as a keypress. It only ever proposes reversible actions, always
behind human approval, and verifies recovery against the same metric that fired.

It works. The alert has fired and healed live, including once at 3:33 AM with nobody
awake. A human-approved drill went from alert to verified recovery in under three
minutes. And we measured the judge against independent labels before trusting it with a
pager: it agreed 38 out of 40 times, with zero false alarms.

## Block B — How we used SigNoz

SigNoz is the whole nervous system, not just a dashboard we bolted on:

- **Traces** — every answer is one trace (prompt, retrieved docs, tokens, and our
  verdict on standard `gen_ai.evaluation.*` attributes). Filter for score < 0.5 and
  you're looking at the exact lie.
- **Logs** — each verdict is also a log event; the "unsupported answer" warning carries
  the trace ID so you can jump straight to the failing span.
- **Dashboards** — two, on the new Dashboards V2 API: one that turns red when the bot
  lies, one that deliberately stays green through the same incident.
- **Alerts** — faithfulness as an SLO with a burn-rate rule, firing a webhook to our
  healer.
- **MCP server** — the brain's entire investigation runs over SigNoz's MCP endpoint; we
  also built the dashboards and alerts through it.
- **Foundry** — one-command install; `casting.yaml` is in the repo and a push script
  recreates the whole dashboard/alert pack on any instance.

## Block C — Experience  ⬜ *(make this yours — a line or two in your own voice)*

Honestly, the best parts were the things that broke. We flipped our "make it lie"
switch and the model just refused — it stayed honest no matter what we told it, which
taught us that real regressions ship as releases, not evil prompts. An overnight run
froze solid while its health flag still said "alive," and our own telemetry is what
diagnosed it. And the night SigNoz caught and fixed an incident at 3:33 AM while we
slept was the moment this stopped feeling like a demo. We wrote up four of these in the
repo — we'd do it again just for what the failures taught us.

---

## Before you submit

- [ ] Blog published (must be a NEW post) → link into field 10
- [ ] Video ≤3 min, covers overview/stack/architecture/demo/learnings → field 8
- [x] Repo public, `casting.yaml` + `casting.yaml.lock` committed
- [x] Disclosures in README + blog
- [ ] Submit (one team member)
