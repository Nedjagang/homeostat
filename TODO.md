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
- [x] Metric: `gen_ai.evaluation.score` histogram, labels = `service.name, eval.name, model, customer.tier, label, prompt.version` (BOUNDED only; `prompt.version` added deliberately — versions are committed artifacts, and score-by-version is the investigation's key chart). No spec metric for eval scores exists yet.
- [x] Span attrs, spec-exact per semantic-conventions-genai: `gen_ai.evaluation.{name, score.value, score.label, explanation}` + `gen_ai.prompt.name`, `prompt.version`, `claim.id`, `customer.tier`. Every verdict ALSO emitted as a `gen_ai.evaluation.result` log event (the spec's blessed shape). Plus `claimpilot.claims.processed{outcome}` so failed claims aren't silent holes in the SLI.
- [ ] Alert webhook JSON → brain `/webhook` (`{alerts:[{status, labels, ...}]}`).
- [x] ClaimPilot `/control`: `pin_prompt_version(version)`, `circuit_break(tool)`, plus live chaos flips (`POST /control/chaos/{flag}`) — one process with the continuous claim loop, live-tested end-to-end (flip → scores tank → pin → recovery).
- [ ] Chaos flag names + expected SigNoz signatures (from `chaos/flags.md`).

---

## Agent A — Agent & Eval (the moat) + video
- [~] `claimpilot/` LangGraph agent: 3–4 tools + RAG over `policies/` (~20 synthetic docs). *(runs end-to-end; 2 tools so far)*
- [x] Write the ~20 policy docs so the sample claims split (7 answerable, 3 unanswerable).
- [~] `telemetry.py` wired (traces+metrics+logs, truststore, flush-on-exit); currently exporting to the remote SigNoz ingester — switch to the local collector (`:4318`) when the Foundry stack is up.
- [~] `prompt.version` on the root span; WARN log on unsupported (carries `trace_id`, exports via OTLP). **(GATE 1)** *(emitting clean; still to prove live in the SigNoz UI)*
- [~] `eval.py` funnel: Tier 0 (deterministic) + Tier 2 judge (gpt-5.6-sol, JSON verdict) wired and proven — baseline all 1.0, overconfident run tanks the 3 unanswerable to 0.0/0.2/0.0. Tier 1 stubbed; judge gating (flagged+2% only) not wired yet.
- [x] Verdict as attributes on the root span + the bounded metric (contract labels incl. `label`, `model`; judge tokens on `gen_ai.evaluation.judge_tokens`).
- [x] **Filter `score<0.5` → drill to the exact lying span with prompt + reason. (GATE 2 — THE MOAT.)** Verified in the UI + used by the brain's investigation.
- [~] Funnel routes only flagged (tier1 lexical) + ~2% calibration to the judge; `eval.route` on every span; judge-token metric feeding the cost panel. **(GATE 2A)** *(live; regression-catch verification in progress)*
- [~] Self-observe: brain stages traced as `homeostat.action` spans under service `homeostat-brain`. **(GATE 6-meta)** *(emitting; UI confirmation pending)*
- [ ] Record the 3-minute video (Day 4).

## Agent B — SigNoz & Data-plane
- [ ] SigNoz via Foundry (`gauge → forge → cast`); **commit `casting.yaml` + `casting.yaml.lock`.**
- [ ] SigNoz MCP server running; API key issued. **(GATE 0)**
- [x] `traditional.json` (stays green) + `agent-quality.json` (faithfulness SLI + grounded ratio + score-by-version + judge/cost panels) — built via the SigNoz MCP against live data (all query shapes dry-run first), exported to `signoz/dashboards/`.
- [~] **Faithfulness SLO pack**: SLI + SLO (98% grounded) + 7.5× fast-burn rule + absolute floor — authored + calibrated (`signoz/alerts/faithfulness-slo.md`), pushable via `signoz/push-packs.py`. Pending: SIGNOZ_API_KEY, live push, fire-during-regression verification, slow-burn companion.
- [ ] `cost-velocity.json` + `judge-budget.json`; all webhook the brain.
- [ ] Webhook channel configured + **Test** passes; tighten window/group-interval for the demo.
- [ ] Log↔span correlation: WARN `unsupported answer` pivots to the failing span.
- [ ] Baseline collector config: redact bodies + tail-sample ~10%; tiered retention. **(GATE 2B)**
- [ ] Export every dashboard/alert as JSON into `signoz/`. **(GATE 3)** import clean + right alert in <1 min.

## Agent C — Brain & Remediation
- [x] `brain/main.py` `/webhook` reachable (+ `/simulate` for local delivery testing); per-incident workers with dedup.
- [x] `investigate()`: bounded MCP playbook that **correlates score↓ with `prompt.version` AND `model`** vs a baseline window + confirms traditional signals stayed green. Live-proven: named v_overconfident @0.82 + the nano downgrade.
- [~] Slack report (Block Kit, evidence links, Approve/Reject over Socket Mode). **(GATE 5a)** *(code proven; delivery blocked until the bot is invited to the channel — `/invite @alerts_for_signoz`)*
- [x] `remediate.py`: `pin_prompt_version` / `circuit_break` (bearer-authed, both reversible).
- [x] `verify.py`: poll the grounded-ratio SLI (10m window, target 0.90); recover → close, else escalate, no thrash.
- [x] Save the regression case to `chaos/regressions/` (first case: 2026-07-24-203648-v_overconfident.json).
- [x] **approve → revert → SLI recovers → regression test saved. (GATE 5)** Drill 2026-07-25 02:04Z: alert→verified recovery in 2m49s (auto-approve drill mode; re-run with a human click pending the Slack invite).
- [ ] (Optional) minimal `viewer/` page with deep links.
- [ ] Deploy brain + claimpilot on the SigNoz VM (webhook becomes container-local; runbook in docs/overnight-runbook.md).

## Agent D — Rigor & Adoption (make it not a toy)
- [~] `chaos/flags.md` library: `prompt_overconfident` (release = prompt+model) and `broken_json_tool` both implemented and verified end-to-end with their heals; `poisoned_chunk` still a stub.
- [~] `chaos/loadgen.py`: implemented (threaded replay + throughput report); volume run + cardinality capture scheduled tonight.
- [~] Judge calibration: `generate.py` batch running (~40 samples across grounded/strong × overconfident/nano); independent labeling + agreement report next. NOTE: labels by the AI assistant, disclosed in the report and blog.
- [ ] `SKILL.md` polish + importable-pack polish (with B) + one-page reproduction guide.
- [x] README credibility checklist accurate; `docs/blog-draft.md` assembled from the four `what-broke/` postmortems (screenshot markers pending captures).
- [~] **calibration report + reproducible failure library + scale evidence committed. (GATE 6)**

---

## Everyone, every evening
- [ ] Write your `docs/what-broke/YYYY-MM-DD-<name>.md` note (honest — this is where credibility is earned).

## Submission (Day 4, submit a day early)
- [ ] Video recorded · README complete · blog published (not AI-slop) · casting files re-run on a clean host.
- [ ] Disclosures present (warm-up prototype + AI-assistant use). Submitted via the hackathon form.
