"""Reversible remediation calls against ClaimPilot's /control endpoint."""
import os
import httpx

CLAIMPILOT = os.getenv("CLAIMPILOT_CONTROL_URL", "http://localhost:8091")


def pin_prompt_version(version: str) -> dict:
    return httpx.post(f"{CLAIMPILOT}/control/pin_prompt_version", params={"version": version}).json()


def circuit_break(tool: str) -> dict:
    return httpx.post(f"{CLAIMPILOT}/control/circuit_break", params={"tool": tool}).json()
