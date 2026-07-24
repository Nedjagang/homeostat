# Homeostat — faithfulness as a first-class signal in SigNoz

**Team BunkBros · Agents of SigNoz (WeMakeDevs × SigNoz) — Track 1: AI & Agent Observability.**

An AI claims agent gives a confident *wrong* answer while every traditional dashboard stays green.
Homeostat makes **answer-faithfulness a golden signal** in SigNoz — an SLI with an SLO and a
burn-rate alert, correlated to the **exact span** — then investigates the regression with grounded
evidence and heals it with a **reversible, human-approved, verified** action. The whole loop is
itself observable in SigNoz.

---

## Architecture

```
 ClaimPilot (LangGraph + RAG) ──OTLP──▶ OTel Collector ──▶ SigNoz (ClickHouse)
   · faithfulness verdict + prompt.version ON the span
   · WARN log (carries trace_id) on an unsupported answer
                                            │ SLO burn-rate alert
                                            ▼
   Brain: investigate via SigNoz MCP → correlate score↓ with prompt.version
        → evidence-linked hypothesis (a clickable query per claim) → Slack (human approves)
                                            │
   Remediate on ClaimPilot /control:  pin_prompt_version(prev)  |  circuit_break(tool)   (reversible)
                                            │
   Verify the SLI recovered → yes: done · no: roll back + escalate → save a regression test
                                            │
   Self-observe: the brain's own cost + every remediation are traced in SigNoz too
```

The demo failure is a **prompt regression**, so the correct heal is an **app-level prompt-version
revert** — reversible, boring, exactly what a real operator would do. No autonomous shell, no
config tricks. Restraint is the point.

---

## Why this isn't a toy

1. Fills a gap SigNoz acknowledged (issues #8865, #1590). OTel-native — spec-exact
   `gen_ai.evaluation.*` span attributes + `gen_ai.evaluation.result` events. Portable, no lock-in.
2. **Faithfulness is an SLI** with an explicit SLO (98% grounded) and a **7.5× burn-rate alert**
   (+ absolute floor) — not a hardcoded threshold. Verified firing AND resolving live, including
   one fully unattended fire→heal→resolve cycle at 3:33 AM.
3. The judge is a **calibrated signal, not ground truth** — agreement measured against independent
   labels (`chaos/calibration/`; labels produced by an AI assistant, disclosed as such).
4. **Reproducible failure classes** (committed chaos flags anyone can flip) — never `if demo: crash`.
   Two classes verified end-to-end: the prompt+model release regression and the broken-tool error spike.
5. **Grounded evidence, no hallucinated RCA** — the brain investigates over the SigNoz MCP with a
   *bounded playbook* (`brain/skill.md`); every report sentence is a number it queried.
6. **Restraint** — two allowlisted reversible actions, human approval over Slack Socket Mode,
   recovery verified against the same SLI that fired, escalate on failure.
7. **Bounded, measured cost** — a three-tier eval funnel (deterministic → lexical → judge) with the
   routing decision on every span (`eval.route`) and judge tokens as their own metric.
8. **Cardinality discipline** — bounded metric labels only (verified at volume with `chaos/loadgen.py`).
9. **Adoption artifacts** — importable dashboard (Dashboards V2 / Perses v6) + alert packs, one
   push script against a fresh SigNoz, a from-zero `docs/how-it-works.md`, and the brain's playbook.
10. **Honest** — four "what genuinely broke" postmortems in `docs/what-broke/` and stated limits.

---

## Repo structure

```
claimpilot/   the AI agent + the eval spine (telemetry, judge funnel, chaos flags, /control)
signoz/       importable dashboard + alert packs (exported JSON) + Query Builder views
brain/        the investigator: alert webhook → MCP → evidence-linked hypothesis → Slack → remediate/verify
chaos/        reproducible failure-class library + load harness + judge-calibration report
viewer/       (optional) a one-page readable trace view that deep-links back into SigNoz
docs/         demo script, blog draft, nightly "what broke" notes
casting.yaml  Foundry deployment config (+ casting.yaml.lock is generated on install — commit both)
```

## Quickstart

1. Install SigNoz via Foundry (`foundryctl gauge → forge`, then compose up — see `casting.yaml`),
   or point at an existing SigNoz ≥ v0.134. SigNoz ≥ v0.134 serves its MCP server at `/mcp`.
2. `cd claimpilot && pip install -r requirements.txt && cp .env.example .env` (fill keys),
   then `uvicorn control:app --port 8091` — claims start flowing.
3. Import the packs: create an API key (UI → Settings), create the `homeostat-brain` webhook
   channel, then `python signoz/push-packs.py` (alerts + Dashboards-V2 dashboards, idempotent).
4. `cd brain && pip install -r requirements.txt && uvicorn main:app --port 8090`; invite the
   Slack bot to your channel.
5. Break it on purpose: `POST /control/chaos/prompt_overconfident?enabled=true` → watch the SLO
   alert fire → the brain's Slack report → click Approve → watch the SLI recover.
   Start `docs/how-it-works.md` if you're new — it assumes zero context.

Full build order, gates, and the 4-person split live in the team build doc (kept out of this public repo).

## Team

Agent & Eval (the moat) · SigNoz & data-plane · Brain & remediation · Rigor & adoption. See the build doc.

---

## Disclosures

- **Prior work:** we prototyped the eval-to-trace idea in our pre-kickoff warm-up task. **This repository is a
  clean-room build — no warm-up or other prior-project code is copied here.**
- **AI assistance:** an AI coding assistant was used during development. All design decisions, code review,
  and the failure/calibration analysis are ours.

## License

MIT — see [LICENSE](./LICENSE).
