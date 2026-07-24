"""Slack surface: evidence-linked incident reports with Approve/Reject buttons.

Approval arrives over Socket Mode (a websocket the brain opens to Slack), so the brain
needs NO public endpoint — it runs next to SigNoz and still gets human decisions.
"""
import json
import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "claimpilot" / ".env")

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

log = logging.getLogger("homeostat.brain")

CHANNEL = os.getenv("SLACK_CHANNEL", "#all-bunkbros-signoz-alerts")
_web = WebClient(token=os.getenv("SLACK_BOT_TOKEN", ""))
_socket: SocketModeClient | None = None

# incident_id -> {"event": Event, "decision": str|None, "user": str|None}
_pending: dict[str, dict] = {}


def _on_socket_request(client: SocketModeClient, req: SocketModeRequest) -> None:
    if req.type != "interactive":
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        return
    client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))  # ack fast
    payload = req.payload
    for action in payload.get("actions", []):
        action_id = action.get("action_id", "")
        if action_id not in ("homeostat_approve", "homeostat_reject"):
            continue
        incident_id = action.get("value", "")
        entry = _pending.get(incident_id)
        user = payload.get("user", {}).get("username") or payload.get("user", {}).get("id", "someone")
        if entry:
            entry["decision"] = "approved" if action_id == "homeostat_approve" else "rejected"
            entry["user"] = user
            entry["event"].set()
        # strike the buttons on the original message so it can't be double-clicked
        container = payload.get("container", {})
        if container.get("channel_id") and container.get("message_ts"):
            verdict = "✅ approved" if action_id == "homeostat_approve" else "🛑 rejected"
            _web.chat_update(channel=container["channel_id"], ts=container["message_ts"],
                             text=f"decision recorded: {verdict} by @{user}",
                             blocks=[{"type": "section",
                                      "text": {"type": "mrkdwn",
                                               "text": f"*Homeostat incident {incident_id}* — "
                                                       f"{verdict} by @{user}"}}])


def start_socket_listener() -> None:
    global _socket
    _socket = SocketModeClient(app_token=os.getenv("SLACK_APP_TOKEN", ""), web_client=_web)
    _socket.socket_mode_request_listeners.append(_on_socket_request)
    _socket.connect()
    log.info("slack socket-mode listener connected")


def post_report(incident_id: str, report: dict, action: dict) -> str | None:
    """Post the evidence-linked report with Approve/Reject. Returns the message thread ts."""
    evidence_lines = "\n".join(
        f"• {e['claim']}  <{e['query_url']}|open in SigNoz>" for e in report.get("evidence", []))
    missing = report.get("missing") or []
    blocks = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": "🧠 Homeostat: faithfulness SLO burning"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{report['summary']}*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": evidence_lines or "_no evidence_"}},
    ]
    if missing:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": "*Could not determine:* " + "; ".join(missing)}]})
    blocks += [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f"*Proposed reversible action:* `{action['name']}({json.dumps(action.get('params', {}))})`"
                    f" — risk: {action['risk']}"}},
        {"type": "actions", "elements": [
            {"type": "button", "style": "primary", "action_id": "homeostat_approve",
             "text": {"type": "plain_text", "text": "Approve heal"}, "value": incident_id},
            {"type": "button", "style": "danger", "action_id": "homeostat_reject",
             "text": {"type": "plain_text", "text": "Reject"}, "value": incident_id},
        ]},
    ]
    try:
        resp = _web.chat_postMessage(channel=CHANNEL, text=report["summary"], blocks=blocks)
        return resp.get("ts")
    except Exception as e:
        # A missing invite or Slack outage must not kill the incident loop — the heal
        # path still works; the report lands in the brain log instead.
        log.error("slack post failed (%s) — report follows:\n%s", e, json.dumps(report, indent=1))
        return None


def wait_approval(incident_id: str, timeout_s: int) -> tuple[str, str | None]:
    """Block until a human clicks. Returns (approved|rejected|timeout, username)."""
    entry = {"event": threading.Event(), "decision": None, "user": None}
    _pending[incident_id] = entry
    entry["event"].wait(timeout=timeout_s)
    _pending.pop(incident_id, None)
    return entry["decision"] or "timeout", entry["user"]


def post_update(text: str, thread_ts: str | None = None) -> None:
    try:
        _web.chat_postMessage(channel=CHANNEL, text=text, thread_ts=thread_ts)
    except Exception:  # a Slack hiccup must never break the heal loop
        log.exception("slack update failed")
