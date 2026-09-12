"""
groq_client.py
--------------
Thin wrapper around the Groq Python SDK for the PitWall RAG pipeline.

Exposes a single function, ``ask_groq``, which accepts pre-built system and
user prompt strings and returns the model's reply as a plain string.

Model
-----
    openai/gpt-oss-20b   (Groq-hosted, fast inference)

Configuration
-------------
``GROQ_API_KEY`` must be set in your ``.env`` file (or the real environment).
See ``.env.example`` for the expected variable name.

Functions
---------
ask_groq(system_prompt, user_prompt, model=DEFAULT_MODEL, max_tokens=1024)
    -> str

Usage (standalone smoke test)
------------------------------
    python utils/groq_client.py
"""

from __future__ import annotations

import os
import pathlib
import sys

from dotenv import load_dotenv
from groq import Groq  # pip install groq

# ── Paths & env ──────────────────────────────────────────────────────────────
ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent

# Load .env from the project root so this module works whether called
# directly (python utils/groq_client.py) or imported from elsewhere.
load_dotenv(ROOT_DIR / ".env")

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_MODEL      = "openai/gpt-oss-20b"
DEFAULT_MAX_TOKENS = 1_024


# ── Client factory ───────────────────────────────────────────────────────────

def _get_client() -> Groq:
    """
    Instantiate a ``Groq`` client using the ``GROQ_API_KEY`` environment
    variable.  Raises ``EnvironmentError`` with a clear message if the key
    is missing so the developer knows exactly what to fix.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file (see .env.example) or export it as an "
            "environment variable before running PitWall."
        )
    # The SDK's default max_retries=2 respects Groq's Retry-After header on
    # 429s, which on the free tier can be 10+ seconds — with up to 2 retries
    # that's 20-30+ seconds of pure dead wait on a SINGLE call before it even
    # fails. One retry is enough to smooth over a transient blip without
    # letting a sustained rate-limit turn into a multi-request pileup; the
    # orchestrator already tolerates an individual agent failing outright.
    return Groq(api_key=api_key, max_retries=1)


# ── Public API ────────────────────────────────────────────────────────────────

def ask_groq(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """
    Send a system + user message pair to a Groq-hosted LLM and return the
    reply as a plain string.

    Parameters
    ----------
    system_prompt : str
        The system-role message that sets context and constraints for the model.
    user_prompt : str
        The user-role message containing retrieved context and the question.
    model : str
        Groq model identifier.  Defaults to ``"openai/gpt-oss-20b"``.
    max_tokens : int
        Upper bound on the number of tokens the model may generate.
        Defaults to 1 024.

    Returns
    -------
    str
        The model's reply text, stripped of leading/trailing whitespace.

    Raises
    ------
    EnvironmentError
        If ``GROQ_API_KEY`` is absent from the environment.
    groq.APIError (and subclasses)
        Propagated as-is if the Groq API returns an error response.
    ValueError
        If either prompt string is empty.
    """
    if not system_prompt or not system_prompt.strip():
        raise ValueError("'system_prompt' must be a non-empty string.")
    if not user_prompt or not user_prompt.strip():
        raise ValueError("'user_prompt' must be a non-empty string.")

    client = _get_client()

    completion = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
    )

    # The Groq SDK mirrors the OpenAI response shape.
    # completion.choices[0].message.content is the reply string.
    reply: str = completion.choices[0].message.content or ""
    return reply.strip()


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== groq_client.py smoke test ===\n")

    sys_prompt = (
        "You are a helpful assistant. Answer only from the context provided. "
        "If the context is insufficient, say 'I don't have enough data to answer that.'"
    )
    usr_prompt = (
        "## Retrieved Context\n\n"
        "### Lap Data [laps]\n"
        "**[Chunk 1 | distance=0.11 | driver=VER, lap_number=32]**\n"
        "Driver: VER | Lap: 32 | Compound: SOFT | LapTime: 1:12.345 | Position: 1\n\n"
        "---\n\n"
        "## Question\n\n"
        "What compound was Verstappen on during lap 32?"
    )

    print("Sending request to Groq...\n")
    try:
        answer = ask_groq(sys_prompt, usr_prompt)
        print("── Response ───────────────────────────────────────────────────")
        print(answer)
    except EnvironmentError as exc:
        print(f"[CONFIG ERROR] {exc}")
    except Exception as exc:
        print(f"[API ERROR] {type(exc).__name__}: {exc}")
