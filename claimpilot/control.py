"""ClaimPilot service: the continuous claim loop + the /control heal surface, ONE process.

They must share a process: /control mutates runtime state (active prompt, circuit
breakers, chaos flags) that the claim loop reads on every iteration. A one-shot batch
(agent.py) can't be healed — by the time the brain acts, the process is gone. This
service is what makes regression -> alert -> heal -> recovery real: claims flow
continuously, a chaos flip degrades them live, a pin heals them live, and the
faithfulness SLI in SigNoz shows both edges.

Every control action opens its own span tagged homeostat.action, so the heal itself
is observable in the same SigNoz (the self-observation beat).

Auth: mutating endpoints require `Authorization: Bearer $CLAIMPILOT_CONTROL_TOKEN`
when that env var is set (it should be, outside local dev — this API repoints the
live prompt). GET /control/state stays open: it is read-only.

Run:   uvicorn control:app --port 8091
Demo:  POST /control/chaos/prompt_overconfident?enabled=true   (the regression)
       POST /control/pin_prompt_version?version=v1_grounded    (the heal)
"""
import json
import logging
import os
import random
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException

import chaos

load_dotenv()  # module-level env reads below need .env before telemetry.py loads it

log = logging.getLogger("claimpilot.control")

CLAIM_INTERVAL = float(os.getenv("CLAIM_INTERVAL_SECONDS", "20"))
CONTROL_TOKEN = os.getenv("CLAIMPILOT_CONTROL_TOKEN", "")
PROMPTS = Path(__file__).parent / "prompts"
CLAIMS_DIR = Path(__file__).parent / "claims"
# The loop prefers the big shuffled pool (realistic dashboards); the 10-claim
# example file stays as the fast deterministic smoke set for `python agent.py`.
CLAIMS_FILE = next(p for p in (CLAIMS_DIR / "claims.pool.json", CLAIMS_DIR / "claims.example.json")
                   if p.exists())

RECENT = deque(maxlen=20)  # last verdicts, for /control/state and quick debugging
_counters = {"processed": 0, "failed": 0}
_last_claim_at: str | None = None
_loop_thread: threading.Thread | None = None


def _claim_loop() -> None:
    global _last_claim_at
    from agent import run_claim_safely  # deferred: import only after init_telemetry()
    claims = [c for c in json.loads(CLAIMS_FILE.read_text(encoding="utf-8")) if "question" in c]
    log.info("claim loop starting: %d claims from %s, interval ~%ss",
             len(claims), CLAIMS_FILE.name, CLAIM_INTERVAL)
    while True:
        batch = claims[:]
        random.shuffle(batch)  # no fixed cycle -> dashboards don't show a synthetic sawtooth
        for claim in batch:
            version = chaos.active_prompt_version()
            verdict = run_claim_safely(claim)
            _last_claim_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if verdict:
                _counters["processed"] += 1
                RECENT.append({"id": claim["id"], "prompt": version, "score": verdict["score"],
                               "label": verdict["label"], "reason": verdict["reason"][:120]})
            else:
                _counters["failed"] += 1
            time.sleep(CLAIM_INTERVAL * random.uniform(0.5, 1.5))  # jitter: no metronome pattern


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _loop_thread
    from telemetry import init_telemetry, shutdown
    init_telemetry()
    _loop_thread = threading.Thread(target=_claim_loop, daemon=True, name="claim-loop")
    _loop_thread.start()
    yield
    shutdown()


app = FastAPI(title="claimpilot-control", lifespan=lifespan)


def require_token(authorization: str | None = Header(None)):
    """Bearer-token check for the mutating endpoints. No token configured = open
    (local dev only — set CLAIMPILOT_CONTROL_TOKEN anywhere that matters)."""
    if CONTROL_TOKEN and authorization != f"Bearer {CONTROL_TOKEN}":
        raise HTTPException(401, "missing or invalid bearer token")


def _action_span(action: str, **attrs):
    """Every control mutation is itself traced — the heal shows up in SigNoz too."""
    from opentelemetry import trace
    span = trace.get_tracer("claimpilot.control").start_span(f"control.{action}")
    span.set_attribute("homeostat.action", action)
    for key, value in attrs.items():
        span.set_attribute(key, value)
    span.end()


@app.post("/control/pin_prompt_version", dependencies=[Depends(require_token)])
def pin_prompt_version(version: str):
    """Revert to a committed prior prompt artifact (prompts/<version>.txt)."""
    if not (PROMPTS / f"{version}.txt").exists():
        raise HTTPException(404, f"unknown prompt version '{version}'")
    chaos.pin_prompt(version)
    _action_span("pin_prompt_version", **{"prompt.version": version})
    log.warning("homeostat.action: pin_prompt_version -> %s", version)
    return {"active_prompt": version}


@app.post("/control/circuit_break", dependencies=[Depends(require_token)])
def circuit_break(tool: str, enabled: bool = True):
    """Disable a misbehaving tool (the agent routes around it). enabled=false closes the
    circuit again — every heal action must be reversible, including this one."""
    if enabled:
        chaos.DISABLED_TOOLS.add(tool)
    else:
        chaos.DISABLED_TOOLS.discard(tool)
    _action_span("circuit_break", **{"tool.name": tool, "circuit.open": enabled})
    log.warning("homeostat.action: circuit_break(%s) -> open=%s", tool, enabled)
    return {"disabled_tools": sorted(chaos.DISABLED_TOOLS)}


@app.post("/control/chaos/{flag}", dependencies=[Depends(require_token)])
def set_chaos(flag: str, enabled: bool = True):
    """Flip a committed chaos flag live (the reproducible failure library)."""
    try:
        chaos.set_flag(flag, enabled)
    except KeyError:
        raise HTTPException(404, f"unknown chaos flag '{flag}' (see chaos/flags.md)")
    _action_span("chaos_flag", **{"chaos.flag": flag, "chaos.enabled": enabled})
    return {"flags": chaos.FLAGS, "active_prompt": chaos.active_prompt_version()}


@app.get("/control/state")
def state():
    return {"active_prompt": chaos.active_prompt_version(),
            "disabled_tools": sorted(chaos.DISABLED_TOOLS),
            "flags": chaos.FLAGS,
            "claims": dict(_counters),
            "loop_alive": bool(_loop_thread and _loop_thread.is_alive()),
            "last_claim_at": _last_claim_at,
            "claims_file": CLAIMS_FILE.name,
            "recent": list(RECENT)}

# run: uvicorn control:app --port 8091
