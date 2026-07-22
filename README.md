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

1. Fills a gap SigNoz acknowledged (issues #8865, #1590). OTel-native `gen_ai.*` — portable, no lock-in.
2. **Faithfulness is an SLI** with an SLO and a **burn-rate/drift alert** — not a hardcoded threshold.
3. The judge is a **calibrated signal, not ground truth** — agreement measured against human labels (`chaos/calibration/`).
4. **Reproducible failure classes** (committed chaos flags anyone can flip) — never `if demo: crash`.
5. **Grounded evidence, no hallucinated RCA** — every brain claim is a clickable SigNoz query.
6. **Restraint** — reversible actions, human-approved, verified recovery, rollback + escalate on failure.
7. **Bounded, measured cost** — a tiered eval funnel + a judge-budget alert; numbers read off the span.
8. **Scales to billions of rows** — metric-cardinality discipline + tiered retention (see the build doc).
9. **Adoption artifacts** — importable dashboard/alert packs + a `SKILL.md` + a readable trace view.
10. **Honest** — a "what genuinely broke" section and stated limits.

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

1. Install SigNoz via Foundry (`foundryctl gauge → forge → cast`); **commit `casting.yaml` and `casting.yaml.lock`**.
2. Run the SigNoz MCP server (`signoz/` notes).
3. `cd claimpilot && pip install -r requirements.txt`; point `OTEL_EXPORTER_OTLP_ENDPOINT` at the collector; run the agent over the sample claims.
4. Import the packs in `signoz/`; confirm the faithfulness SLO alert fires when you flip the prompt-chaos flag.
5. Run the brain (`brain/`); wire the alert webhook to it.

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
