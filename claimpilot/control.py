"""ClaimPilot control endpoint — the reversible, human-approved heal surface.
The brain calls these AFTER approval; both actions are reversible and observable."""
from fastapi import FastAPI
import chaos

app = FastAPI(title="claimpilot-control")


@app.post("/control/pin_prompt_version")
def pin_prompt_version(version: str):
    """Revert to a committed prior prompt artifact (prompts/<version>.txt)."""
    chaos.ACTIVE_PROMPT = version
    return {"active_prompt": version}


@app.post("/control/circuit_break")
def circuit_break(tool: str):
    """Disable a misbehaving tool; the agent routes around it."""
    chaos.DISABLED_TOOLS.add(tool)
    return {"disabled_tools": sorted(chaos.DISABLED_TOOLS)}


@app.get("/control/state")
def state():
    return {"active_prompt": chaos.ACTIVE_PROMPT, "disabled_tools": sorted(chaos.DISABLED_TOOLS)}

# run: uvicorn control:app --port 8091
