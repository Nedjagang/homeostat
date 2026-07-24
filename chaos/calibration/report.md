# Judge calibration report

**Question answered here:** how often does the LLM judge's verdict agree with an
independent reading of the same evidence? The judge is a *measured signal, not assumed
ground truth* — this report is the measurement.

## Disclosure (read first)

The independent labels were produced by an **AI assistant (Claude)**, not human
annotators, reading each sample's question, full retrieved context, and answer, with the
complete 20-clause policy corpus available for reference. The judge is a *different*
model (`gpt-5.6-sol` via Azure) with a different rubric and no access to the corpus
beyond the retrieved context. This measures **agreement between two independent
graders**, not correctness against human truth. Treat the numbers accordingly.

## Setup

- 40 samples from `generate.py`: 20 claims (12 answerable, 8 unanswerable) × 2
  conditions — the honest release (`v1_grounded` prompt, strong model) and the chaos
  release (`v_overconfident` prompt, nano model).
- Judge: score < 0.5 ⇒ `unsupported`. Labeler: `unsupported` when the answer asserts
  determinations/facts/guidance the retrieved context does not support.
- Raw data: `samples.json` (generated), `labels.json` (labeled, with per-sample notes).

## Results

|                       | judge: grounded | judge: unsupported |
|-----------------------|-----------------|--------------------|
| **label: grounded**   | 33              | 0                  |
| **label: unsupported**| 2               | 5                  |

- **Percent agreement: 95% (38/40)**
- **Cohen's κ: 0.80** (substantial agreement beyond chance)
- **Judge precision on `unsupported`: 5/5 = 100%** — when the judge says unsupported,
  the labeler always agreed. No false alarms → the SLO alert doesn't cry wolf.
- **Judge recall on `unsupported`: 5/7 = 71%** — the judge missed two answers the
  labeler flagged. Both misses lean the same way (below).

Condition sanity check: the honest release produced 20/20 grounded under both graders;
all disagreement lives in the chaos release, where it should.

## The two disagreements — one shared blind spot

1. **CLM-106 / "does AU-220 cover me driving a rental car in Mexico?"** (judge 1.00,
   label unsupported). The nano model answered about rental *reimbursement* — every
   sentence corpus-true — while implying it answered the Mexico/territory question.
   A **relevance dodge**: faithfulness-only judging scores each sentence against the
   context and finds nothing false. Notably, Tier 1 *also* clears it (lexical overlap
   0.63, high — because the dodge quotes the context!). Both defenses share the blind
   spot by construction.
2. **CLM-108 / grace period** (judge 0.55, label unsupported). "It is safe to assume
   coverage could be immediately affected" is speculation presented as guidance. The
   judge scored the accurate first sentence and shrugged at the speculation —
   a borderline case sitting exactly at the threshold.

**Implication:** the funnel's stated coverage is *faithfulness* (is the answer supported
by the context), not *answer relevance* (did it answer the question asked). Relevance
dodges evade both the lexical tier and a faithfulness-only judge. The OTel GenAI
conventions anticipate multiple named evaluations per response — adding an
`answer_relevance` evaluation alongside `judge_faithfulness` is the concrete next step,
and this report is the evidence for why.

## Tier-1 threshold validation (bonus)

Against these labels, the 0.55 suspicion threshold routes **7/7 labeled-unsupported
answers to the judge except the relevance dodge** (6/7; the dodge scores 0.63 and no
lexical threshold can catch it — see above). Every fabrication scored ≤ 0.30, leaving a
0.25 margin below the threshold. Cost side: 6 of 24 healthy answerable answers fell
below 0.55 and were judged unnecessarily — the price of the safety margin, visible live
on the `eval.route` span attribute.

## Limits

Small n (40), synthetic corpus, one domain, AI labeler, judge and agent share a model
provider. The right reading: *the judge and an independent grader almost never disagree
on what this corpus's fabrications look like, and never in the false-alarm direction* —
good enough to alert on, not a warranty of truth.
