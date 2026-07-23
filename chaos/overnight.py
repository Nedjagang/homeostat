"""Overnight variety scheduler: drives ClaimPilot's /control API on a fixed cycle so
long unattended runs produce analyzable telemetry — several full regression->heal
incident cycles, a healthy alternate prompt version (score-by-version history), and
one tool-failure incident — instead of hours of flat 1.0.

Runs as its own small process next to the service. Every action lands in SigNoz too:
/control traces each mutation as a homeostat.action span.

    python chaos/overnight.py            # uses CLAIMPILOT_CONTROL_URL + CLAIMPILOT_CONTROL_TOKEN

The 3-hour cycle, repeated forever:
    0:00 - 1:00   healthy on v1_grounded (baseline)
    1:00 - 1:40   healthy on v2_concise  (a second good version in the history)
    1:40          back to v1_grounded
    2:00 - 2:20   CHAOS: prompt_overconfident  -> faithfulness tanks, SLO alert fires
    2:20          HEAL: pin v1_grounded        -> alert resolves
    2:40 - 2:50   CHAOS: broken_json_tool      -> error-rate incident (traditional signals move)
    2:50          HEAL: circuit_break lookup_policy, then close circuit + flag off
    3:00          cycle repeats

Expect ~4 faithfulness incidents and ~4 tool incidents per 12h night, each with a
clean recovery edge — exactly the shapes burn-rate/SLO analysis needs.
"""
import logging
import os
import time

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / "claimpilot" / ".env")

import requests

BASE = os.getenv("CLAIMPILOT_CONTROL_URL", "http://localhost:8091").rstrip("/")
TOKEN = os.getenv("CLAIMPILOT_CONTROL_TOKEN", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("overnight")

# (minute_in_cycle, description, [(method_path, params), ...])
CYCLE_MINUTES = 180
SCHEDULE = [
    (60,  "healthy alternate version", [("/control/pin_prompt_version", {"version": "v2_concise"})]),
    (100, "back to baseline version",  [("/control/pin_prompt_version", {"version": "v1_grounded"})]),
    (120, "INJECT prompt regression",  [("/control/chaos/prompt_overconfident", {"enabled": "true"})]),
    (140, "HEAL prompt regression",    [("/control/chaos/prompt_overconfident", {"enabled": "false"}),
                                        ("/control/pin_prompt_version", {"version": "v1_grounded"})]),
    (160, "INJECT broken tool",        [("/control/chaos/broken_json_tool", {"enabled": "true"})]),
    (170, "HEAL broken tool",          [("/control/circuit_break", {"tool": "lookup_policy", "enabled": "true"}),
                                        ("/control/chaos/broken_json_tool", {"enabled": "false"}),
                                        ("/control/circuit_break", {"tool": "lookup_policy", "enabled": "false"})]),
]


def act(path: str, params: dict) -> None:
    try:
        resp = requests.post(f"{BASE}{path}", params=params,
                             headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10)
        log.info("POST %s %s -> %s %s", path, params, resp.status_code, resp.text[:120])
    except requests.RequestException as e:  # service restarting etc. — skip, next cycle retries
        log.warning("POST %s failed: %s", path, e)


def main() -> None:
    log.info("overnight scheduler against %s — %d-minute cycle", BASE, CYCLE_MINUTES)
    start = time.time()
    fired: set = set()
    while True:
        cycle_minute = (time.time() - start) / 60 % CYCLE_MINUTES
        cycle_number = int((time.time() - start) / 60 // CYCLE_MINUTES)
        for minute, desc, actions in SCHEDULE:
            key = (cycle_number, minute)
            if cycle_minute >= minute and key not in fired:
                fired.add(key)
                log.info("[cycle %d, t+%dm] %s", cycle_number, minute, desc)
                for path, params in actions:
                    act(path, params)
        time.sleep(20)


if __name__ == "__main__":
    main()
