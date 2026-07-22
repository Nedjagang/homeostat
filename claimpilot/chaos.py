"""Reproducible failure classes as committed flags (never `if demo: crash`).
Flip via env vars or the /control endpoint; each maps to one healable failure.
See ../chaos/flags.md for the full library and expected SigNoz signatures."""
import os

FLAGS = {
    # The DEMO OPENER — pure quality failure: latency/tokens stay green, faithfulness tanks.
    "prompt_overconfident": os.getenv("CHAOS_PROMPT_OVERCONFIDENT", "0") == "1",
    # Separate beats (these DO move token/error metrics — don't mix into the opener):
    "broken_json_tool": os.getenv("CHAOS_BROKEN_JSON_TOOL", "0") == "1",
    "poisoned_chunk": os.getenv("CHAOS_POISONED_CHUNK", "0") == "1",
}

# runtime state the healer toggles
ACTIVE_PROMPT = "v_overconfident" if FLAGS["prompt_overconfident"] else "v1_grounded"
DISABLED_TOOLS: set[str] = set()


def active_prompt_version() -> str:
    return ACTIVE_PROMPT
