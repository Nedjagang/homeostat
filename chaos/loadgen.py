"""Replay claims at volume to prove the data-plane contract holds under load:
metric cardinality stays bounded (fixed label sets, no per-claim labels) and the
pipeline keeps up. Telemetry IS emitted — that's the point of the proof.

    python chaos/loadgen.py [n_claims] [concurrency]

Capture series-cardinality numbers before/after via the SigNoz MCP
(signoz_check_metric_cardinality) and record them in the loadgen section of the docs.
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CLAIMPILOT = Path(__file__).resolve().parent.parent / "claimpilot"
sys.path.insert(0, str(CLAIMPILOT))

from telemetry import init_telemetry, shutdown  # noqa: E402


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    concurrency = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    init_telemetry()
    from agent import run_claim_safely  # after telemetry init

    pool = json.loads((CLAIMPILOT / "claims" / "claims.pool.json").read_text(encoding="utf-8"))
    claims = [c for c in pool if "question" in c]
    batch = [claims[i % len(claims)] for i in range(n)]

    ok = err = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as pool_exec:
        for verdict in pool_exec.map(run_claim_safely, batch):
            if verdict:
                ok += 1
            else:
                err += 1
            done = ok + err
            if done % 10 == 0:
                rate = done / (time.time() - start) * 60
                print(f"{done}/{n} claims ({ok} ok, {err} err) — {rate:.1f} claims/min")
    elapsed = time.time() - start
    print(f"\nDONE: {n} claims in {elapsed/60:.1f} min "
          f"({n/elapsed*60:.1f} claims/min at concurrency {concurrency}); {err} errors")
    shutdown()


if __name__ == "__main__":
    main()
