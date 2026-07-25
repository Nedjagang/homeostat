"""Voice-call approval channel: ring the on-call human, read the incident aloud,
gather a keypress — 1 approves the heal, 2 rejects.

No inbound webhook needed (the brain may live behind NAT): a Twilio Studio Flow hosts
the call logic in Twilio's cloud, and we POLL the execution context over REST for the
gathered digit. Run `python voice.py setup` once to create the flow and print its SID.

Env (claimpilot/.env): TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER,
ONCALL_PHONE, TWILIO_FLOW_SID (from setup).
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "claimpilot" / ".env")

import requests

log = logging.getLogger("homeostat.brain")

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
ONCALL_PHONE = os.getenv("ONCALL_PHONE", "")
FLOW_SID = os.getenv("TWILIO_FLOW_SID", "")
STUDIO = "https://studio.twilio.com/v2"


def configured() -> bool:
    return all([ACCOUNT_SID, AUTH_TOKEN, FROM_NUMBER, ONCALL_PHONE, FLOW_SID])


# The IVR, defined as data: say the incident, gather one digit (two attempts),
# confirm what was chosen. The brain reads widgets.gather_approval.Digits afterwards.
FLOW_DEFINITION = {
    "description": "Homeostat incident approval call",
    "initial_state": "Trigger",
    "flags": {"allow_concurrent_calls": True},
    "states": [
        {"name": "Trigger", "type": "trigger",
         "transitions": [{"event": "incomingMessage"},
                         {"event": "incomingCall", "next": "gather_approval"},
                         {"event": "incomingConversationMessage"},
                         {"event": "incomingRequest", "next": "gather_approval"},
                         {"event": "incomingParent"}],
         "properties": {"offset": {"x": 0, "y": 0}}},
        {"name": "gather_approval", "type": "gather-input-on-call",
         "transitions": [{"event": "keypress", "next": "confirm"},
                         {"event": "speech"},
                         {"event": "timeout"}],
         "properties": {"offset": {"x": 0, "y": 200},
                        "say": ("{{flow.data.message | default: 'This is Homeostat, the claim "
                                "agent monitor. Answer quality alert. A prompt release has "
                                "regressed answer quality. Latency and errors are normal. "
                                "Proposed fix: roll back to the last healthy version. Details "
                                "are in the Slack thread. This action is reversible. "
                                "Press 1 to approve the fix. Press 2 to reject.'}}"),
                        "voice": "Polly.Matthew",
                        "language": "en-US",
                        "number_of_digits": 1,
                        "timeout": 10,
                        "loop": 2,
                        "stop_gather": True,
                        "gather_language": "en",
                        "speech_timeout": "auto",
                        "speech_model": "default",
                        "profanity_filter": "true"}},
        {"name": "confirm", "type": "say-play",
         "transitions": [{"event": "audioComplete"}],
         "properties": {"offset": {"x": 0, "y": 400},
                        "voice": "Polly.Matthew",
                        "language": "en-US",
                        "say": ('{% if widgets.gather_approval.Digits == "1" %}'
                                "Approved. Applying the heal now and verifying recovery. Goodbye."
                                "{% else %}"
                                "Rejected. No action will be taken. Goodbye."
                                "{% endif %}"),
                        "loop": 1}},
    ],
}


def setup_flow() -> str:
    """One-time: create (and publish) the Studio Flow. Prints the SID for .env."""
    resp = requests.post(f"{STUDIO}/Flows", auth=(ACCOUNT_SID, AUTH_TOKEN), data={
        "FriendlyName": "homeostat-approval",
        "Status": "published",
        "Definition": json.dumps(FLOW_DEFINITION),
    }, timeout=30)
    if resp.status_code >= 300:
        raise SystemExit(f"flow creation failed {resp.status_code}: {resp.text[:500]}")
    sid = resp.json()["sid"]
    print(f"Studio Flow created and published: {sid}")
    print(f"Add to claimpilot/.env:  TWILIO_FLOW_SID={sid}")
    return sid


def _spoken_summary(report: dict, action: dict) -> str:
    """What the call says. Short, spellable, no jargon the ear can't parse."""
    offending = (report.get("offending_version") or "unknown").replace("_", " ")
    target = (action.get("params", {}).get("version") or "previous version").replace("_", " ")
    return (f"This is Homeostat, the claim agent monitor. Answer quality alert. "
            f"Version {offending} is producing unsupported answers. "
            f"Latency and errors are normal, so this is a quality regression. "
            f"Proposed fix: roll back to version {target}. This action is reversible. "
            f"Press 1 to approve the fix. Press 2 to reject.")


def call_for_approval(report: dict, action: dict, timeout_s: int = 180) -> tuple[str, str]:
    """Place the call (plain Calls API — proven path) and hand it to the Studio flow via
    Twilio's flow-webhook URL; then poll the resulting execution's context for the
    keypress. Returns (approved|rejected|timeout|error, detail)."""
    placed_at = time.time()
    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Calls.json",
            auth=(ACCOUNT_SID, AUTH_TOKEN), data={
                "To": ONCALL_PHONE, "From": FROM_NUMBER,
                "Url": f"https://webhooks.twilio.com/v1/Accounts/{ACCOUNT_SID}/Flows/{FLOW_SID}",
                "Timeout": 25,  # ring seconds before giving up
            }, timeout=30)
        body = resp.json()
        if resp.status_code >= 300:
            return "error", f"call placement failed {resp.status_code}: {body.get('message', '')[:200]}"
        call_sid = body["sid"]
        log.info("voice approval call placed: %s to …%s", call_sid, ONCALL_PHONE[-4:])
    except requests.RequestException as e:
        return "error", f"call placement failed: {e}"

    execution_sid = None
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(5)
        try:
            if execution_sid is None:
                # The flow execution appears once the call is answered; find OURS —
                # match the contact AND require it to be newer than our placement,
                # otherwise a stale execution from an earlier call gets picked up.
                from datetime import datetime, timezone
                execs = requests.get(f"{STUDIO}/Flows/{FLOW_SID}/Executions?PageSize=5",
                                     auth=(ACCOUNT_SID, AUTH_TOKEN), timeout=15).json()
                for ex in execs.get("executions", []):
                    created = ex.get("date_created", "")
                    if ex.get("contact_channel_address") != ONCALL_PHONE or not created:
                        continue
                    created_ts = datetime.fromisoformat(
                        created.replace("Z", "+00:00")).timestamp()
                    if created_ts >= placed_at - 30:
                        execution_sid = ex["sid"]
                        break
            if execution_sid:
                ctx = requests.get(
                    f"{STUDIO}/Flows/{FLOW_SID}/Executions/{execution_sid}/Context",
                    auth=(ACCOUNT_SID, AUTH_TOKEN), timeout=15).json()
                digits = (ctx.get("context", {}).get("widgets", {})
                          .get("gather_approval", {}).get("Digits"))
                if digits == "1":
                    return "approved", "phone keypress 1"
                if digits is not None:
                    return "rejected", f"phone keypress {digits}"
            call = requests.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Calls/{call_sid}.json",
                auth=(ACCOUNT_SID, AUTH_TOKEN), timeout=15).json()
            if call.get("status") in ("busy", "no-answer", "failed", "canceled"):
                return "timeout", f"call {call.get('status')}"
            if call.get("status") == "completed" and execution_sid is None:
                return "timeout", "call completed without reaching the flow"
        except requests.RequestException:
            pass  # transient — keep polling until the deadline
    return "timeout", "no keypress before deadline"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        if not (ACCOUNT_SID and AUTH_TOKEN):
            raise SystemExit("set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in claimpilot/.env first")
        setup_flow()
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        logging.basicConfig(level=logging.INFO)
        fake_report = {"offending_version": "v_overconfident", "prev_version": "v2_concise"}
        fake_action = {"name": "pin_prompt_version", "params": {"version": "v2_concise"}, "risk": "risky"}
        print("placing test call...", call_for_approval(fake_report, fake_action))
    else:
        print("usage: python voice.py setup | test")
