"""The brain: SigNoz alert webhook -> investigate via the SigNoz MCP -> evidence-linked
hypothesis -> Slack -> reversible remediation -> verify. Never authors freeform commands;
it selects a reversible, allowlisted action and posts the evidence behind it."""
from fastapi import FastAPI, Request

from remediate import pin_prompt_version, circuit_break
from verify import verify_recovery
from slack import post_report

app = FastAPI(title="homeostat-brain")


async def investigate(alert: dict) -> dict:
    """Query the SigNoz MCP (bounded: service + tight window, aggregates before raw spans).
    CORRELATE: pull the low-score spans, observe they share a prompt.version, conclude that
    version regressed. Every finding carries a clickable SigNoz query/trace link + missing info.
    Returns {summary, evidence:[{claim, query_url}], offending_version, prev_version, missing:[...]}"""
    # TODO: MCP loop using skill.md conventions.
    raise NotImplementedError


def choose_action(report: dict) -> dict:
    """Map finding -> a reversible, allowlisted action. No freeform config/commands."""
    if report.get("offending_version"):
        return {"name": "pin_prompt_version", "params": {"version": report["prev_version"]}, "risk": "risky"}
    return {"name": "explain_only", "params": {}, "risk": "safe"}


def apply(action: dict) -> None:
    if action["name"] == "pin_prompt_version":
        pin_prompt_version(action["params"]["version"])
    elif action["name"] == "circuit_break":
        circuit_break(action["params"]["tool"])
    # explain_only: do nothing — a human fixes it (the loop still tells the story)


@app.post("/webhook")
async def webhook(req: Request):
    payload = await req.json()
    for alert in payload.get("alerts", []):
        if alert.get("status") != "firing":
            continue
        report = await investigate(alert)
        action = choose_action(report)
        post_report(report, action)                 # evidence links + proposed action -> Slack
        if action["risk"] == "safe":
            apply(action)
            verify_recovery(report)
        # risky: wait for Slack approval, then apply(action) + verify_recovery(report)
    return {"ok": True}

# run: uvicorn main:app --port 8090
