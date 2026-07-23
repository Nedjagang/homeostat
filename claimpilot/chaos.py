"""Reproducible failure classes as committed flags (never `if demo: crash`).
Flip via env vars at startup, or live via the /control endpoint; each flag maps to one
healable failure. See ../chaos/flags.md for the full library and expected SigNoz signatures."""
import os

from dotenv import load_dotenv

load_dotenv()  # this module reads env at import time and may be imported before the app's own load

GROUNDED_PROMPT = "v1_grounded"
OVERCONFIDENT_PROMPT = "v_overconfident"

# A prompt version is a RELEASE: prompt text + model config. The v_overconfident release
# didn't just loosen the wording — it also downgraded the deployment to cut costs. That
# combination is what makes the regression reproducible: the strong model resists an
# overconfident prompt and keeps abstaining (measured — see docs/what-broke/), while the
# weak one complies and fabricates. pin_prompt_version(v1_grounded) therefore heals both.
DEFAULT_MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
VERSION_MODELS = {
    OVERCONFIDENT_PROMPT: os.getenv("CHAOS_OVERCONFIDENT_MODEL") or DEFAULT_MODEL,
}

FLAGS = {
    # The DEMO OPENER — pure quality failure: latency/tokens stay green, faithfulness tanks.
    "prompt_overconfident": os.getenv("CHAOS_PROMPT_OVERCONFIDENT", "0") == "1",
    # Separate beats (these DO move token/error metrics — don't mix into the opener):
    "broken_json_tool": os.getenv("CHAOS_BROKEN_JSON_TOOL", "0") == "1",
    "poisoned_chunk": os.getenv("CHAOS_POISONED_CHUNK", "0") == "1",
}

# Runtime state. ACTIVE_PROMPT is the single source of truth for which prompt ships:
# the chaos flag flips it (the regression), pin_prompt() overwrites it (the heal).
ACTIVE_PROMPT = OVERCONFIDENT_PROMPT if FLAGS["prompt_overconfident"] else GROUNDED_PROMPT
DISABLED_TOOLS: set[str] = set()


def active_prompt_version() -> str:
    return ACTIVE_PROMPT


def active_model() -> str:
    """The answering model shipped by the active release (prompt version)."""
    return VERSION_MODELS.get(ACTIVE_PROMPT, DEFAULT_MODEL)


def set_flag(name: str, enabled: bool) -> None:
    """Flip a chaos flag at runtime (the /control surface calls this)."""
    if name not in FLAGS:
        raise KeyError(name)
    FLAGS[name] = enabled
    if name == "prompt_overconfident":
        global ACTIVE_PROMPT
        ACTIVE_PROMPT = OVERCONFIDENT_PROMPT if enabled else GROUNDED_PROMPT


def pin_prompt(version: str) -> None:
    """The heal: pin a committed prompt artifact regardless of chaos flags."""
    global ACTIVE_PROMPT
    ACTIVE_PROMPT = version
