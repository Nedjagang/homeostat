"""Slack report + approval. Every claim in the report is a clickable SigNoz query link."""
import os
import httpx

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")


def post_report(report: dict, action: dict) -> None:
    lines = [f"*Homeostat*: {report.get('summary', 'quality regression detected')}"]
    for e in report.get("evidence", []):
        lines.append(f"• {e['claim']} — <{e['query_url']}|open in SigNoz>")
    if report.get("missing"):
        lines.append("*Missing / could not determine:* " + "; ".join(report["missing"]))
    lines.append(f"*Proposed action:* `{action['name']}` {action.get('params', {})} "
                 f"({action['risk']}) — approve to apply.")
    if SLACK_WEBHOOK:
        httpx.post(SLACK_WEBHOOK, json={"text": "\n".join(lines)})
    else:
        print("\n".join(lines))  # dev fallback
