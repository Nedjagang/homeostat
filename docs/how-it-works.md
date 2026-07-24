# How Homeostat / ClaimPilot works — from zero

This document explains everything that is **already built and proven working** in this
repository, for a reader who knows nothing about the project. It avoids analogies and
defines every term the first time it is used. The parts of the plan that are **not built
yet** are listed at the end so you know where the boundary is.

---

## 1. What this project is

ClaimPilot is a small AI program that answers insurance-claim questions
("Is a burst pipe covered under policy HP-100?") by reading a folder of policy documents.

AI programs like this have a specific failure mode: the language model sometimes produces a
**confident answer that is not supported by the documents it read**. The answer looks fine,
arrives fast, and costs the normal amount — so every traditional monitoring signal (latency,
errors, token counts) stays green while the system is giving customers wrong information.

This project makes that failure **visible and fixable** in SigNoz, an open-source
observability platform:

1. Every answer is **scored** for whether the documents actually support it.
2. The score is attached to the **exact trace** of the request that produced the answer.
3. The failure can be **reproduced on demand** (a "chaos flag") and **healed at runtime**
   through an HTTP endpoint — without restarting anything.

All three points have been run and verified end-to-end against a live SigNoz.

---

## 2. Words you need

| Term | Meaning here |
|---|---|
| **LLM** | Large language model. A program that takes text in and produces text out. We call one hosted on Azure OpenAI (deployment name `gpt-5.6-sol`). |
| **Prompt** | The text sent to the LLM. The **system prompt** is the standing instruction that tells the LLM how to behave; the user message is the question. |
| **Agent** | A loop in which the LLM may either answer directly or ask to run a **tool**, see the tool's result, and continue until it produces a final answer. |
| **Tool** | A Python function the LLM is allowed to call. Ours look up policy documents. |
| **Retrieval / context** | Searching documents for text relevant to the question. Whatever text the tools returned to the LLM during one claim is called that claim's **context**. |
| **Hallucination / unsupported answer** | An answer whose content is not backed by the retrieved context. |
| **LLM judge** | A second, separate LLM call whose only job is to grade the first answer: "is this answer supported by this context?" It returns a score from 0 to 1 and a one-line reason. |
| **OpenTelemetry (OTel)** | An open standard for emitting telemetry from a program. Telemetry comes in three kinds: **traces**, **metrics**, and **logs**. |
| **Span** | One recorded operation with a start time, end time, and key/value **attributes**. |
| **Trace** | All the spans from one request, linked in a parent/child tree and sharing one `trace_id`. One processed claim = one trace. |
| **Metric** | A named number recorded over time (for example: every faithfulness score), used for charts and alerts. Metrics carry a small set of **labels** (key/value tags). |
| **OTLP** | The OpenTelemetry wire protocol. Our program sends traces, metrics, and logs over OTLP/HTTP. |
| **SigNoz** | The observability backend that receives all of this and gives you a UI to search traces, chart metrics, read logs, and define alerts. Ours runs self-hosted on an Azure VM. |
| **OpenLIT** | A library that automatically creates spans for every LLM call and tool call made through the OpenAI SDK / LangChain — including the prompt text, the completion text, and token counts — so we don't write that code by hand. |
| **Chaos flag** | A committed on/off switch that reproduces one specific, realistic failure on demand. Not a random crash — a named, repeatable failure class. |

---

## 3. Architecture — what is built today

```
            ClaimPilot service — ONE Python process (started via control.py)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                                                                              │
 │   claim loop (background thread)         /control HTTP API (port 8091)      │
 │   shuffled claims from             ┌──   POST /control/chaos/{flag}         │
 │   claims.pool.json, jittered pace  │     POST /control/pin_prompt_version   │
 │                 │                  │     POST /control/circuit_break        │
 │                 ▼                  │     GET  /control/state                │
 │   ┌───────── process_claim ────────┼──┐                                     │
 │   │ 1. read runtime state ◄────────┘  │   (the API mutates the SAME state   │
 │   │    (chaos.py: which prompt is     │    the loop reads — that is why     │
 │   │    active, which tools disabled)  │    both live in one process)        │
 │   │ 2. load prompts/<version>.txt    │                                     │
 │   │ 3. run the agent (agent.py)      │                                     │
 │   │     ├─ LLM: Azure OpenAI          │                                     │
 │   │     │       gpt-5.6-sol           │                                     │
 │   │     └─ tools: lookup_policy,      │                                     │
 │   │        list_exclusions            │                                     │
 │   │           └─ retriever.py: TF-IDF │                                     │
 │   │              search over the 20   │                                     │
 │   │              files in policies/   │                                     │
 │   │ 4. score the answer (eval.py)    │                                     │
 │   │     ├─ Tier 0: deterministic,     │                                     │
 │   │     │  free check                 │                                     │
 │   │     ├─ Tier 1: lexical overlap    │                                     │
 │   │     │  proxy, free — only         │                                     │
 │   │     │  suspicious answers go on   │                                     │
 │   │     └─ Tier 2: LLM judge          │                                     │
 │   │        (score 0..1 + reason)      │                                     │
 │   └───────────────────────────────────┘                                     │
 │                 │                                                            │
 │   telemetry.py — OpenTelemetry SDK setup + OpenLIT auto-instrumentation      │
 └─────────────────┼────────────────────────────────────────────────────────────┘
                   │   OTLP over HTTPS: traces + metrics + logs
                   ▼
     SigNoz, self-hosted on an Azure VM  (https://signoz.apteancloud.dev)
     · traces: one per claim, with prompts, tool calls, token counts, eval verdict
     · metrics: gen_ai.evaluation.score, gen_ai.evaluation.judge_tokens,
                claimpilot.claims.processed
     · logs:   a gen_ai.evaluation.result event per verdict, plus WARN
               "unsupported answer" carrying the trace_id of the failing trace
```

There is also a second entry point, `agent.py`, which runs the same `process_claim`
pipeline once over all 10 sample claims and exits (a batch run). It exists for smoke
tests; the service above is the real system.

---

## 4. The files

| File | What it does |
|---|---|
| `claimpilot/control.py` | The service. Starts telemetry, starts the claim loop in a background thread, and serves the `/control` HTTP API on port 8091. |
| `claimpilot/agent.py` | `process_claim()` — runs one claim through the agent and the eval funnel. Also runnable directly as a one-shot batch (`python agent.py`). |
| `claimpilot/retriever.py` | Document search. Scores each policy file against the query with TF-IDF cosine similarity, filters by policy id, returns the top 3 above a minimum relevance of 0.08 — or nothing if no file is relevant enough. |
| `claimpilot/eval.py` | The scoring funnel (Tier 0 check, Tier 2 judge) and all verdict emission: span attributes, metric, WARN log. |
| `claimpilot/chaos.py` | The runtime state: which prompt version is active, which chaos flags are on, which tools are circuit-broken. Both env vars (at startup) and `/control` (at runtime) set it. |
| `claimpilot/telemetry.py` | OpenTelemetry wiring: exporters for traces/metrics/logs pointed at `OTEL_EXPORTER_OTLP_ENDPOINT`, OpenLIT initialization, and a `shutdown()` that flushes buffers (required for short batch runs). |
| `claimpilot/prompts/v1_grounded.txt` | The safe system prompt: answer only from retrieved context; if the context is insufficient, say exactly "I don't have enough information in the policy to determine this." |
| `claimpilot/prompts/v2_concise.txt` | A newer healthy prompt iteration (shorter, decision-first answers, same grounding rules). Exists so the prompt history has more than one good version — realistic regressions happen between routine versions. |
| `claimpilot/prompts/v_overconfident.txt` | The bad system prompt (a committed chaos artifact): always give a confident, definitive answer; never refuse. |
| `claimpilot/policies/*.md` | 20 synthetic policy documents, one clause per file, across two policies: HP-100 (home) and AU-220 (auto). |
| `claimpilot/claims/claims.pool.json` | The service loop's pool: ~44 claims (33 answerable, 11 deliberately not answerable), shuffled every cycle with a jittered interval so dashboards don't show a repeating pattern. |
| `claimpilot/claims/claims.example.json` | 10 sample claims: 7 answerable, 3 not answerable (CLM-101/102/103). Kept small and fixed as the smoke set for `python agent.py`. |
| `claimpilot/.env` | Secrets and endpoints (git-ignored): Azure OpenAI key/endpoint/deployment, OTLP endpoint. `.env.example` documents every variable. |
| `docker-compose.apps.yaml` | Runs the service (and optional one-shot batch) as containers next to a SigNoz stack. |

---

## 5. One claim's journey, step by step

This is what happens for every single claim, both in the loop and in a batch run.

1. **Pick the prompt.** `chaos.active_prompt_version()` returns the currently active
   prompt version — normally `v1_grounded`, or `v_overconfident` if the chaos flag is on,
   or whatever an operator pinned last. The matching file in `prompts/` is loaded as the
   system prompt.

2. **Open the root span.** A span named `claim.process` is started. Everything else that
   happens for this claim becomes a child of it, so SigNoz shows it all as one trace.
   Three attributes are set immediately: `claim.id`, `customer.tier`, and
   `prompt.version`. The last one matters most: it is what lets you later correlate
   "scores dropped" with "the prompt changed".

3. **Run the agent.** The claim question and the system prompt go to the LLM. The LLM may
   call the tools:
   - `lookup_policy(policy_id, query)` — retrieves the 3 most relevant policy clauses.
   - `list_exclusions(policy_id)` — returns all exclusion clauses for a policy.
   The text the tools return is collected; that collection is this claim's **context**.
   The loop continues until the LLM produces a final answer. OpenLIT records every LLM
   call and tool call as child spans automatically, including the full prompt and
   completion text and token counts.

4. **Score the answer** (`evaluate_and_emit` in `eval.py`) — a three-tier funnel that
   keeps the expensive judge off the answers that don't need it:
   - **Tier 0 (free, deterministic).** If the context is empty AND the answer does not
     contain the exact abstention sentence, the answer is provably unsupported: the agent
     asserted something with nothing retrieved to back it. Score 0.0, done, no LLM cost.
   - **Tier 1 (free, lexical).** Word-overlap similarity between the answer and the
     retrieved context. Grounded answers quote the clause they relied on, so healthy
     overlap is high; fabricated amounts and decisions share little vocabulary with the
     context. High-overlap answers are cleared without a judge call (binary pass, with
     the raw overlap value kept on the span); low-overlap answers go to the judge.
   - **Tier 2 (the judge).** A second LLM call grades the answer against the context and
     returns a score from 0 to 1 with a one-line reason. It runs on Tier-1-flagged
     answers plus a ~2% random calibration sample that keeps the cheap tiers honest.
     Score below 0.5 is labeled `unsupported`. If the judge call fails, the claim is not
     blocked — the verdict falls back to the cheap tiers and says so honestly.
   - The routing decision (`tier0:fail`, `tier1:clear`, `judge:suspicious`,
     `judge:calibration`) lands on the span as `eval.route`, so the funnel's economics
     are visible per-claim. `EVAL_JUDGE_MODE=all` disables the gating.

5. **Emit the verdict everywhere it is needed:**
   - **On the root span** (for drill-down in one exact trace), using the exact attribute
     names from the OpenTelemetry GenAI semantic conventions: `gen_ai.evaluation.name`,
     `gen_ai.evaluation.score.value`, `gen_ai.evaluation.score.label`,
     `gen_ai.evaluation.explanation`.
   - **As a `gen_ai.evaluation.result` event** — a log record in the same trace context.
     This is the emission shape the conventions actually standardize; we emit it in
     addition to the span attributes.
   - **As a metric** (for charts and alerts): the score is recorded on the
     `gen_ai.evaluation.score` histogram with only bounded, low-cardinality labels
     (`service.name`, `eval.name`, `model`, `customer.tier`, `label`, `prompt.version`).
     Never the claim id, trace id, or explanation text — unbounded label values would
     explode the metric database. The conventions define no metric for evaluation
     scores yet, so this metric name is ours.
   - **As a WARN log** when unsupported: message `unsupported answer`, carrying the
     `trace_id`. In SigNoz you can go from this log line straight to the failing trace.
   - **Judge cost**: the judge's token usage is added to the
     `gen_ai.evaluation.judge_tokens` counter metric.
   - **Claim outcome**: every claim increments `claimpilot.claims.processed` with an
     `outcome` label (`ok` or `error`), so a claim that crashes is visible as an error
     count instead of being a silent hole in the score series.
   - **Verdict counter**: every verdict also increments `gen_ai.evaluation.verdicts`
     with the same labels. The SLO's good-events ratio (grounded verdicts divided by all
     verdicts) is computed from this counter — counter rates are the most reliably
     queryable primitive for alerting.

---

## 6. The failure experiment (proven)

The 3 unanswerable claims are the trap. Under the grounded prompt the agent abstains on
them, and an honest abstention scores 1.0. Under the overconfident prompt the agent invents
a confident decision, and the funnel catches it.

Measured results:

| Run | Answerable claims (7) | Unanswerable claims (3) |
|---|---|---|
| Baseline, `v1_grounded` | all 1.0 | all 1.0 (abstained) |
| Regression, `v_overconfident` | 0.9 – 1.0 | **0.0 / 0.2 / 0.0** |

The critical property: during the regression, latency, error counts, and token usage stay
normal. Only the faithfulness score moves. That is the observability gap this project fills.

One honest caveat, also observed: the judge's score for the same claim varies between runs
(one claim scored 0.2 in one run and 0.96 in another, because the agent words its answer
differently each time). Single-claim scores are noisy; any alert must therefore be defined
on the **average score over a time window**, not on individual claims.

---

## 7. The live control surface (proven)

Because the claim loop and the `/control` API share one process, an operator (or later, an
automated investigator) can change the running system's behavior instantly:

```bash
# see current state: active prompt, chaos flags, disabled tools, recent verdicts
curl http://localhost:8091/control/state

# inject the failure: switch the live system prompt to the overconfident version
curl -X POST "http://localhost:8091/control/chaos/prompt_overconfident?enabled=true"

# heal it: pin the prompt back to the safe committed version
curl -X POST "http://localhost:8091/control/pin_prompt_version?version=v1_grounded"

# disable a misbehaving tool (the agent is told the tool is unavailable)
curl -X POST "http://localhost:8091/control/circuit_break?tool=lookup_policy"

# a second, different failure class: the policy-lookup tool starts returning
# malformed JSON (tool errors + retries — this one DOES move the traditional
# signals, unlike the prompt regression; its heal is the circuit breaker above)
curl -X POST "http://localhost:8091/control/chaos/broken_json_tool?enabled=true"
```

When the environment variable `CLAIMPILOT_CONTROL_TOKEN` is set, every state-changing
endpoint above additionally requires the header
`Authorization: Bearer <that token>` and answers `401` without it. `GET /control/state`
stays open because it is read-only. If the variable is unset (local development), no
authentication is enforced.

Verified live, in order, on one uninterrupted process: grounded claim scored 1.0 → chaos
flag flipped over HTTP → next unanswerable claim scored 0.0 `unsupported` → prompt pinned
back → the same claim on the next cycle abstained and scored 1.0 again.

Two details worth knowing:
- A pin **overrides** a still-enabled chaos flag. The flag records that the failure was
  injected; the pin is the operator's override. That mirrors how a real prompt rollback
  works.
- Every control action creates its own span tagged `homeostat.action`, so the healing
  actions are themselves visible in SigNoz alongside the damage they fixed.

---

## 8. How to run it

```bash
cd homeostat/claimpilot
pip install -r requirements.txt
cp .env.example .env        # then fill in real values

# one-shot batch over the 10 sample claims (smoke test)
python agent.py

# the real thing: continuous service + control API
uvicorn control:app --port 8091
```

Environment variables that matter (see `.env.example` for all):

| Variable | Purpose |
|---|---|
| `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` | Azure OpenAI access. |
| `AZURE_OPENAI_DEPLOYMENT` | Which model deployment answers claims. Deliberately **not** named `MODEL`: Windows environment variables are case-insensitive and some laptops ship a factory-set `Model=<number>`, which would silently win. |
| `AZURE_OPENAI_JUDGE_DEPLOYMENT` | Which deployment judges answers (defaults to the same). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Where telemetry goes. Currently the SigNoz VM (`https://signoz.apteancloud.dev/otlp`); becomes `http://localhost:4318` when a local collector is used. |
| `CLAIM_INTERVAL_SECONDS` | Pause between claims in the loop (default 20, jittered ±50%). Lower = denser data = more Azure token spend. |
| `CLAIMPILOT_CONTROL_TOKEN` | Bearer token required by the mutating `/control` endpoints. Unset = auth off (local dev only). |
| `CHAOS_PROMPT_OVERCONFIDENT=1` | Start with the failure already injected (same effect as the HTTP flip). |

---

## 9. The brain (`brain/`) — the part that heals

A second, separate service. Its whole loop:

1. **Receive** the SigNoz alert webhook (`POST /webhook` on port 8090). The alert
   channel `homeostat-brain` is already configured in SigNoz and carries both fire and
   resolve notifications.
2. **Investigate** through the SigNoz MCP server with a *fixed, bounded playbook*
   (`brain/skill.md`): faithfulness score by `prompt.version` in the incident window vs
   a baseline window, the same by `model`, and a check that the traditional signals
   (claim error rate, p99 latency) did NOT move. The brain cannot ask an unbounded
   question, so it cannot hallucinate a root cause — every claim in its report carries
   the numbers it was computed from.
3. **Report** to Slack as an evidence-linked message with **Approve heal / Reject**
   buttons. Button clicks arrive over Slack Socket Mode — a websocket the brain opens
   outward — so the brain needs no public endpoint.
4. **Heal** only after a human clicks approve (its entire write surface is the two
   reversible `/control` actions). `BRAIN_AUTO_APPROVE=1` exists solely for unattended
   drills and labels itself as such everywhere.
5. **Verify** by polling the grounded-ratio SLI until it clears 0.90 (or escalate after
   15 minutes), then save the incident as a reproducible regression case in
   `chaos/regressions/`.
6. The brain traces itself into the same SigNoz as `homeostat-brain` — every stage is a
   span tagged `homeostat.action`, so the healer is visible next to the damage it fixed.

Run it: `cd brain && pip install -r requirements.txt && uvicorn main:app --port 8090`.
`POST /simulate` injects a canned firing alert for local testing.

---

## 10. Not built yet (the boundary)

- **Deploy on the SigNoz VM** — the brain and ClaimPilot belong next to SigNoz (the
  alert webhook can then reach the brain by container name; a laptop cannot accept that
  inbound connection). The compose file and runbook exist; the deployment hasn't happened.
- **Tier-1 upgrade** — the lexical-overlap proxy works but is deliberately simple;
  embedding cosine or a local NLI model is the planned upgrade behind the same seam.
- **Local SigNoz via Foundry** (`casting.yaml`) — a reproducible local install of the
  whole SigNoz stack, so anyone can run this repo without our VM. Pinned to the same
  version as the VM (v0.134.0) but not yet validated on a clean host.
- **Cost alerts** (`cost-velocity`, `judge-budget`) — panels exist; the alert rules don't.
