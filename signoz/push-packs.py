"""Push the committed alert + dashboard packs to a SigNoz instance (create-or-update by name).

SigNoz has no alert-import UI and the new Dashboards V2 (Perses v6) schema is API-first,
so this script IS the import path (GATE 3: a fresh instance lights up in under a minute).
Idempotent — safe to re-run after editing any pack file.

Usage:
    export SIGNOZ_API_KEY=<UI -> Settings -> API Keys>       # or put it in claimpilot/.env
    export SIGNOZ_BASE_URL=https://signoz.example.com        # default: the dev VM
    python signoz/push-packs.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# claimpilot/.env is the single place secrets live; load it if present.
load_dotenv(Path(__file__).resolve().parent.parent / "claimpilot" / ".env")

# Internal endpoints have an OS-trusted (not certifi-trusted) cert chain — same fix as
# claimpilot/telemetry.py. Must run before requests binds its SSLContext.
import truststore

truststore.inject_into_ssl()

import requests

BASE = os.getenv("SIGNOZ_BASE_URL", "https://signoz.apteancloud.dev").rstrip("/")
API_KEY = os.getenv("SIGNOZ_API_KEY", "")
ALERTS_DIR = Path(__file__).resolve().parent / "alerts"
DASHBOARDS_DIR = Path(__file__).resolve().parent / "dashboards"

if not API_KEY or API_KEY == "REPLACE_ME":
    sys.exit("SIGNOZ_API_KEY is not set (SigNoz UI -> Settings -> API Keys).")

session = requests.Session()
session.headers.update({"SIGNOZ-API-KEY": API_KEY, "Content-Type": "application/json"})


def channel_exists(name: str) -> bool:
    resp = session.get(f"{BASE}/api/v1/channels", timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data") or []
    return any(ch.get("name") == name for ch in data)


def existing_rules() -> dict[str, str]:
    """Map alert name -> rule id for everything already on the server (v2 rules API)."""
    resp = session.get(f"{BASE}/api/v2/rules", timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data", payload)
    rules = data.get("rules", data) if isinstance(data, dict) else data
    out = {}
    for rule in rules or []:
        name = rule.get("alert") or rule.get("data", {}).get("alert")
        rule_id = rule.get("id")
        if name and rule_id is not None:
            out[name] = str(rule_id)
    return out


def push_rule(body: dict, rule_id: str | None) -> None:
    if rule_id:
        resp = session.put(f"{BASE}/api/v2/rules/{rule_id}", json=body, timeout=30)
        action = f"updated (id={rule_id})"
    else:
        resp = session.post(f"{BASE}/api/v2/rules", json=body, timeout=30)
        action = "created"
    if resp.status_code >= 300:
        print(f"  FAILED {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)
    print(f"  {action}")


def push_dashboards() -> None:
    """Create-or-update the Dashboards V2 (schemaVersion v6) pack by Perses name."""
    resp = session.get(f"{BASE}/api/v2/dashboards?limit=100", timeout=30)
    resp.raise_for_status()
    have = {d.get("name"): d.get("id")
            for d in resp.json().get("data", {}).get("dashboards", []) if d.get("name")}
    for path in sorted(DASHBOARDS_DIR.glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        name = body.get("name", path.stem)
        print(f"{path.name}: '{name}'")
        if name in have:
            resp = session.put(f"{BASE}/api/v2/dashboards/{have[name]}", json=body, timeout=30)
            action = f"updated (id={have[name]})"
        else:
            resp = session.post(f"{BASE}/api/v2/dashboards", json=body, timeout=30)
            action = "created"
        if resp.status_code >= 300:
            print(f"  FAILED {resp.status_code}: {resp.text[:400]}")
            sys.exit(1)
        print(f"  {action}")


def main() -> None:
    # The rules route to the homeostat-brain webhook channel; SigNoz refuses rules
    # whose channels don't exist, so fail with instructions instead of a cryptic 400.
    if not channel_exists("homeostat-brain"):
        sys.exit("notification channel 'homeostat-brain' does not exist on the target.\n"
                 "Create it first (UI: Alerts -> Notification Channels -> webhook, or the\n"
                 "SigNoz MCP signoz_create_notification_channel tool): type=webhook,\n"
                 "url=http://homeostat-brain:8090/webhook")
    have = existing_rules()
    files = sorted(ALERTS_DIR.glob("*.json"))
    if not files:
        sys.exit(f"no rule files in {ALERTS_DIR}")
    print(f"target: {BASE} ({len(have)} rules already present)")
    for path in files:
        body = json.loads(path.read_text(encoding="utf-8"))
        name = body["alert"]
        print(f"{path.name}: '{name}'")
        push_rule(body, have.get(name))
    push_dashboards()
    print("done — check Alerts and Dashboards in the SigNoz UI.")


if __name__ == "__main__":
    main()
