"""Post-remediation verification: did the faithfulness SLI actually recover?
One verdict, no thrashing — recovered means the windowed grounded ratio is back above
the healthy line; anything else escalates to a human. Either way the incident becomes
a saved regression case in chaos/regressions/."""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import signoz_client as sz
import slack

log = logging.getLogger("homeostat.brain")

REGRESSIONS_DIR = Path(__file__).resolve().parent.parent / "chaos" / "regressions"
RECOVERY_TARGET = 0.90          # alert threshold 0.85 + margin
VERIFY_WINDOW_MS = 10 * 60_000  # judge recovery on the same window the alert evaluates


def current_grounded_ratio() -> float | None:
    now_ms = int(time.time() * 1000)
    return sz.grounded_ratio(now_ms - VERIFY_WINDOW_MS, now_ms)


def verify_recovery(report: dict, thread_ts: str | None,
                    timeout_s: int = 15 * 60, poll_s: int = 60) -> bool:
    """Poll the SLI until it clears RECOVERY_TARGET or the deadline passes."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(poll_s)
        ratio = current_grounded_ratio()
        log.info("verify: grounded ratio now %s (target %.2f)", ratio, RECOVERY_TARGET)
        if ratio is not None and ratio >= RECOVERY_TARGET:
            slack.post_update(f"✅ verified: grounded ratio recovered to {ratio:.2f} "
                              f"(target {RECOVERY_TARGET}). Incident closed.", thread_ts)
            save_regression_case(report, outcome="recovered")
            return True
    ratio = current_grounded_ratio()
    slack.post_update(f"🚨 NOT recovered after {timeout_s // 60} min "
                      f"(grounded ratio {ratio if ratio is None else f'{ratio:.2f}'}). "
                      f"The pin stays applied (it is the safe state); a human needs to look. "
                      f"Escalating.", thread_ts)
    save_regression_case(report, outcome="escalated")
    return False


def save_regression_case(report: dict, outcome: str) -> None:
    """Persist the incident as a reproducible regression case."""
    REGRESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    case = {
        "captured_at": stamp,
        "outcome": outcome,
        "offending_version": report.get("offending_version"),
        "reverted_to": report.get("prev_version"),
        "summary": report.get("summary"),
        "reproduce": {
            "inject": "POST /control/chaos/prompt_overconfident?enabled=true",
            "expected_breach": "grounded ratio < 0.85 over 10m -> 'Faithfulness SLO fast burn' fires",
            "heal": f"POST /control/pin_prompt_version?version={report.get('prev_version')}",
            "expected_recovery": f"grounded ratio >= {RECOVERY_TARGET} within ~15m",
        },
        "evidence": report.get("evidence", []),
    }
    path = REGRESSIONS_DIR / f"{stamp}-{report.get('offending_version') or 'unknown'}.json"
    path.write_text(json.dumps(case, indent=2), encoding="utf-8")
    log.info("regression case saved: %s", path.name)
