# 3-minute demo script (paced — lead with the deterministic beat)

1. **Green world.** Show `traditional.json` — all green — while ClaimPilot approves a bad claim.
   *"We were monitoring the wrong layer."*
2. **Reveal** `agent-quality.json`; faithfulness is dipping.
3. **Money shot (deterministic — lead here if anything is shaky):** Query Builder →
   `gen_ai.evaluation.score < 0.5` → click → the exact lying span: prompt + RAG chunks + judge
   reason. Pivot to the correlated WARN log (`trace_id`).
4. **Trigger:** flip `CHAOS_PROMPT_OVERCONFIDENT`. Faithfulness SLI breaches SLO; latency/tokens
   stay green. The **burn-rate alert** fires (window pre-tightened for the demo).
5. **Investigate (pre-staged for pacing):** the brain's Slack hypothesis —
   *"prompt.version oc-1 regressed faithfulness"* — with a clickable query; open it on camera.
6. **Heal:** approve the revert in Slack → `pin_prompt_version(v1_grounded)` → the SLI climbs back →
   the case is saved as a regression test.
7. **Close:** *"faithfulness is now a golden signal with an SLO; every fix was a reversible,
   human-approved, verified action — and the whole loop is observable in SigNoz."*

**Pacing rules:** the back half is inherently slow (LLM latency + human approval). Lead with the
deterministic drill (3), pre-stage the firing alert + the brain's hypothesis, keep the live segment
to approve→revert→recover with a tightened recovery window. **Capture fallback screenshots of every
step** in case the live run stalls.
