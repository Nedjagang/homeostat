"""Reversible remediation calls against ClaimPilot's /control endpoint.
The brain never authors freeform commands — these two allowlisted, reversible actions
are its entire write surface, and both require the bearer token."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "claimpilot" / ".env")

import requests

CLAIMPILOT = os.getenv("CLAIMPILOT_CONTROL_URL", "http://localhost:8091").rstrip("/")
_HEADERS = {"Authorization": f"Bearer {os.getenv('CLAIMPILOT_CONTROL_TOKEN', '')}"}


def pin_prompt_version(version: str) -> dict:
    resp = requests.post(f"{CLAIMPILOT}/control/pin_prompt_version",
                         params={"version": version}, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def circuit_break(tool: str, enabled: bool = True) -> dict:
    resp = requests.post(f"{CLAIMPILOT}/control/circuit_break",
                         params={"tool": tool, "enabled": str(enabled).lower()},
                         headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()
