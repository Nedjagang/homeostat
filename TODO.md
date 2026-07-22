# TODO — Team BunkBros (per-agent build checklist)

Four owners ("agents"), each owns one vertical and one headline gate. Check items as you pass them.
Whatever gate you last passed is a complete submission — **never cut the moat (A/Gate 2) or the
green-dashboard/lying-span beat.** Full detail + code snippets live in the build doc.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · **(GATE)** = prove it live before moving on.

---

## Day 0 — shared, do together first (30 min)
- [ ] New clean repo (this folder). `git init` here — **do NOT commit into the warm-up repo.**
- [ ] Push to GitHub (private until submission if you prefer).
- [ ] Fill `LICENSE` year/owner (done: BunkBros 2026) and the README disclosures.
- [ ] **Lock the integration contract** (below) so B/C/D can build against it without waiting on A.
- [ ] Create your `.env` (git-ignored): LLM keys, `SLACK_WEBHOOK_URL`, `SIGNOZ_API_KEY`, `CLAIMPILOT_CONTROL_URL`.

### Integration contract (the seams — agree once, don't drift)
- [ ] Metric: `gen_ai.evaluation.score`, labels = `service.name, eval.name, model, customer.tier, label` (BOUNDED only).
- [ ] Span attrs: `gen_ai.evaluation.{name,score,label,reason?}`, `prompt.version`, `claim.id`, `customer.tier`.
- [ ] Alert webhook JSON → brain `/webhook` (`{alerts:[{status, labels, ...}]}`).
- [ ] ClaimPilot `/control`: `pin_prompt_version(version)`, `circuit_break(tool)`.
- [ ] Chaos flag names + expected SigNoz signatures (from `chaos/flags.md`).

---

## Agent A — Agent & Eval (the moat) + video
- [ ] `claimpilot/` LangGraph agent: 3–4 tools + RAG over `policies/` (~20 synthetic docs).
- [ ] Write the ~20 policy docs so the sample claims split (7 answerable, 3 unanswerable).
- [ ] `telemetry.py` wired; export to the **collector** (`:4318`), not straight to SigNoz.
- [ ] `prompt.version` on the root span; WARN log on unsupported (carries `trace_id`). **(GATE 1)**
- [ ] `eval.py` funnel: Tier 0 (deterministic) + Tier 1 (cheap proxy) + Tier 2 (Haiku judge, structured output, `max_tokens≈256`).
- [ ] Verdict as attributes on the root span + the bounded metric.
- [ ] **Filter `score<0.5` → drill to the exact lying span with prompt + reason. (GATE 2 — THE MOAT, make it flawless.)**
- [ ] Funnel routes only flagged + ~2% calibration to the judge; "judge $/1,000" panel data present. **(GATE 2A)**
- [ ] Self-observe: brain cost + `homeostat.action` visible (with C). **(GATE 6-meta)**
- [ ] Record the 3-minute video (Day 4).

## Agent B — SigNoz & Data-plane
- [ ] SigNoz via Foundry (`gauge → forge → cast`); **commit `casting.yaml` + `casting.yaml.lock`.**
- [ ] SigNoz MCP server running; API key issued. **(GATE 0)**
- [ ] `traditional.json` (stays green) + `agent-quality.json` (faithfulness SLI, judge $/1k, etc.).
- [ ] **`faithfulness-slo.json`**: SLI + SLO + burn-rate/relative-drop alert (+ absolute floor). Not a magic 0.5.
- [ ] `cost-velocity.json` + `judge-budget.json`; all webhook the brain.
- [ ] Webhook channel configured + **Test** passes; tighten window/group-interval for the demo.
- [ ] Log↔span correlation: WARN `unsupported answer` pivots to the failing span.
- [ ] Baseline collector config: redact bodies + tail-sample ~10%; tiered retention. **(GATE 2B)**
- [ ] Export every dashboard/alert as JSON into `signoz/`. **(GATE 3)** import clean + right alert in <1 min.

## Agent C — Brain & Remediation
- [ ] `brain/main.py` `/webhook` reachable; `skill.md` bounded-query rules followed.
- [ ] `investigate()`: MCP loop that **correlates score↓ with `prompt.version`**; evidence = clickable queries.
- [ ] Slack report with a query link per claim + a proposed reversible action. **(GATE 5a)**
- [ ] `remediate.py`: `pin_prompt_version` / `circuit_break` against ClaimPilot `/control`.
- [ ] `verify.py`: poll the faithfulness SLI; recover → done, else roll back + escalate (no thrash).
- [ ] Save the regression case to `chaos/regressions/`.
- [ ] **approve → revert → SLI recovers → regression test saved. (GATE 5)** + a non-recovering case rolls back.
- [ ] (Optional) minimal `viewer/` page with deep links.

## Agent D — Rigor & Adoption (make it not a toy)
- [ ] `chaos/flags.md` library implemented; each flag reproduces its failure on demand.
- [ ] `chaos/loadgen.py`: replay at volume; capture bounded cardinality/disk numbers (scale evidence).
- [ ] Judge calibration: hand-label ~30–50 answers; measure judge agreement; write `chaos/calibration/report.md`.
- [ ] `SKILL.md` polish + importable-pack polish (with B) + one-page reproduction guide.
- [ ] README credibility checklist accurate; assemble `docs/blog-draft.md` from `docs/what-broke/` notes.
- [ ] **calibration report + reproducible failure library + scale evidence committed. (GATE 6)**

---

## Everyone, every evening
- [ ] Write your `docs/what-broke/YYYY-MM-DD-<name>.md` note (honest — this is where credibility is earned).

## Submission (Day 4, submit a day early)
- [ ] Video recorded · README complete · blog published (not AI-slop) · casting files re-run on a clean host.
- [ ] Disclosures present (warm-up prototype + AI-assistant use). Submitted via the hackathon form.
