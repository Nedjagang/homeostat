"""Generate the judge-calibration sample set: (question, context, answer, judge verdict)
across the behavior grid — grounded/strong vs overconfident/nano — WITHOUT touching the
running service or emitting telemetry (no init_telemetry, direct function calls).

Output: chaos/calibration/samples.json — one record per (claim, condition). An
independent labeler then marks each answer grounded/unsupported from the question +
context + answer alone, and report.md measures agreement with the judge.

    python chaos/calibration/generate.py [n_answerable] [n_unanswerable]
"""
import json
import sys
import time
from pathlib import Path

CLAIMPILOT = Path(__file__).resolve().parent.parent.parent / "claimpilot"
sys.path.insert(0, str(CLAIMPILOT))

import chaos                      # noqa: E402
from agent import run_agent, load_prompt   # noqa: E402
from eval import judge, tier0, tier1_proxy  # noqa: E402

OUT = Path(__file__).resolve().parent / "samples.json"

CONDITIONS = [
    ("v1_grounded", None),                       # honest baseline, strong model
    ("v_overconfident", "downgrade"),            # the chaos release (prompt + nano model)
]


def main() -> None:
    n_ans = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    n_unans = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    pool = json.loads((CLAIMPILOT / "claims" / "claims.pool.json").read_text(encoding="utf-8"))
    claims = [c for c in pool if "question" in c]
    answerable = [c for c in claims if not c["id"].startswith("CLM-1")][:n_ans]
    unanswerable = [c for c in claims if c["id"].startswith("CLM-1")][:n_unans]
    batch = answerable + unanswerable

    samples = []
    for version, downgrade in CONDITIONS:
        # Drive the same release semantics the service uses.
        chaos.set_flag("prompt_overconfident", version == "v_overconfident")
        system_prompt = load_prompt(version)
        for claim in batch:
            try:
                t0 = time.time()
                answer, context = run_agent(claim, system_prompt)
                verdict = judge(answer, context)
                samples.append({
                    "claim_id": claim["id"],
                    "unanswerable": claim["id"].startswith("CLM-1"),
                    "prompt_version": version,
                    "model": chaos.active_model(),
                    "question": claim["question"],
                    "context": context,
                    "answer": answer,
                    "tier0_pass": tier0(answer, context),
                    "tier1_cosine": round(tier1_proxy(answer, context), 4),
                    "judge_score": verdict["score"],
                    "judge_reason": verdict["reason"],
                    "latency_s": round(time.time() - t0, 1),
                })
                print(f"{version:>16} {claim['id']}: judge={verdict['score']:.2f} "
                      f"t1={samples[-1]['tier1_cosine']:.2f}")
            except Exception as e:  # one bad sample shouldn't sink the batch
                print(f"{version:>16} {claim['id']}: FAILED — {e}")
    chaos.set_flag("prompt_overconfident", False)

    OUT.write_text(json.dumps(samples, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(samples)} samples -> {OUT}")


if __name__ == "__main__":
    main()
