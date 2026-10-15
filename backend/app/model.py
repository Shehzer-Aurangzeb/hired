"""Calls the LLM: Gemini first, OpenRouter's free pool as fallback.
No retries, only failover, since free tiers are rationed per day."""

import contextvars
import json
import re
import subprocess
from typing import Any

import httpx
from fastapi import HTTPException

from .settings import Settings, get_settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"


# Which model answered the call in progress. A ContextVar rather than a global
# because sync routes run on a threadpool, and two requests must not see each
# other's answer.
served: contextvars.ContextVar[str] = contextvars.ContextVar("served", default="")

TIMEOUT = 60.0
# A local call generates at about 10 tokens a second, and a long posting can
# want 1,500 of them.
LOCAL_TIMEOUT = 600.0

# A loaded 8B model is itself about a third of 16GB, so the floor is what is
# left beyond it. Matches the figure wa2trello settled on.
MIN_FREE_PCT = 15
MIN_BATTERY_PCT = 30

# Pinned to IPv4: httpx tries IPv6 addresses one by one, and on a network with
# broken IPv6 that took ~64s before falling back. A v4 source address skips them.
_CLIENT = httpx.Client(
    timeout=TIMEOUT,
    transport=httpx.HTTPTransport(local_address="0.0.0.0"),
)

# Localhost, so none of the IPv6 reasoning above applies; only the patience does.
_LOCAL = httpx.Client(timeout=LOCAL_TIMEOUT)


def unhealthy() -> str | None:
    """
    Why it is a bad moment to run a model on this machine, or None. macOS only;
    elsewhere it never objects, since the figures come from pmset and sysctl.
    """
    def sh(*cmd: str) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except Exception:  # noqa: BLE001
            return ""

    battery = sh("pmset", "-g", "batt")
    charge = re.search(r"(\d+)%", battery)
    if battery and "AC Power" not in battery and charge and int(charge[1]) < MIN_BATTERY_PCT:
        return f"the battery is at {charge[1]}%, plug the charger in"

    # ponytail: pmset reports OS-level throttling only; real temperatures need
    # sudo powermetrics, which a web request has no business asking for.
    thermal = sh("pmset", "-g", "therm")
    limit = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", thermal)
    if limit and int(limit[1]) < 100:
        return "the Mac is thermally throttling, let it cool"

    free = sh("sysctl", "-n", "kern.memorystatus_level").strip()
    if free.isdigit() and int(free) < MIN_FREE_PCT:
        return f"only {free}% of memory is free"
    return None


def generate_json(
    prompt: str,
    schema: dict[str, Any],
    turns: list[tuple[str, str]] | None = None,
    local_first: bool = False,
) -> dict[str, Any]:
    """
    Return one JSON object matching `schema`, or raise HTTPException with a readable reason.

    `turns` is a conversation as (role, text) pairs, role being "user" or "model".
    Sent as real turns rather than a transcript quoted inside `prompt`: a model
    treats what it said itself as its own, and quoted text as background reading.

    `local_first` for work where being thorough beats being quick. Reading a
    posting is that: measured at 90% of the named requirements against Gemini's
    49%, for about 39 seconds against 4.
    """
    settings = get_settings()

    if settings.demo:
        # A demo must not spend a rationed call, and must work with no network.
        from . import demo

        served.set("demo")
        return demo.answer(schema)

    providers = [("gemini", settings.gemini_api_key), ("ollama", settings.ollama_model)]
    if local_first:
        providers.reverse()
    usable = [(name, _) for name, _ in providers if _]
    if not usable:
        raise HTTPException(503, "No model is configured on this instance.")

    for n, (name, _) in enumerate(usable):
        try:
            if name == "gemini":
                served.set(settings.gemini_model)
                return _gemini(prompt, schema, settings, turns)
            served.set(settings.ollama_model)
            return _ollama(prompt, schema, settings, turns)
        except HTTPException:
            if n == len(usable) - 1:
                raise
    raise HTTPException(503, "No model is configured on this instance.")


def _turns(turns: list[tuple[str, str]] | None, assistant: str) -> list[dict[str, str]]:
    """The conversation, with a short ack so the briefing reads as a turn of its own.

    # ponytail: no merging of consecutive same-role turns. Ask alternates by
    # construction; merge them here if a caller ever sends two in a row.
    """
    if not turns:
        return []
    out = [{"role": assistant, "text": "Understood."}]
    out += [{"role": assistant if role == "model" else "user", "text": text} for role, text in turns]
    return out


def _ollama(
    prompt: str,
    schema: dict[str, Any],
    settings: Settings,
    turns: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """The model on this machine. No key, no quota, no third party."""
    if reason := unhealthy():
        raise HTTPException(503, f"Not running a local model right now: {reason}")

    body = {
        "model": settings.ollama_model,
        "stream": False,
        "format": schema,
        # Reasoning tokens cost the same as useful ones, and generation is the
        # whole expense locally. Extraction is reading, not reasoning.
        "think": False,
        "messages": [{"role": "user", "content": prompt}]
        + [
            {"role": turn["role"], "content": turn["text"]}
            for turn in _turns(turns, "assistant")
        ],
    }
    try:
        response = _LOCAL.post(f"{settings.ollama_url}/api/chat", json=body)
        if response.status_code >= 400 and "think" in body:
            body.pop("think")  # the model has no thinking mode to turn off
            response = _LOCAL.post(f"{settings.ollama_url}/api/chat", json=body)
    except httpx.TimeoutException as error:
        raise HTTPException(504, "The local model took too long.") from error
    except httpx.HTTPError as error:
        raise HTTPException(
            503, "Could not reach ollama. Start it with `ollama serve`."
        ) from error

    if response.status_code == 404:
        raise HTTPException(
            502, f"No model called {settings.ollama_model}. Pull it with `ollama pull`."
        )
    if response.status_code >= 400:
        raise HTTPException(502, f"The local model refused the request. {_message(response)}")

    try:
        return json.loads(response.json()["message"]["content"])
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            502, f"{settings.ollama_model} returned something unreadable."
        ) from error


def _gemini(
    prompt: str,
    schema: dict[str, Any],
    settings: Settings,
    turns: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    try:
        response = _CLIENT.post(
            f"{GEMINI}/{settings.gemini_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}]
                + [
                    {"role": turn["role"], "parts": [{"text": turn["text"]}]}
                    for turn in _turns(turns, "model")
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                },
            },
        )
    except httpx.TimeoutException as error:
        raise HTTPException(504, "The model took too long. Try again.") from error
    except httpx.HTTPError as error:
        raise HTTPException(502, "Could not reach the model.") from error

    if response.status_code == 429:
        raise HTTPException(429, f"Gemini refused on rate. {_limit(response)}")
    if response.status_code == 404:
        # Retired model name; the error body names the replacement.
        raise HTTPException(502, f"{_message(response)} Set HIRED_GEMINI_MODEL.")
    if response.status_code >= 400:
        raise HTTPException(502, f"The model refused the request. {_message(response)}")

    return _first_json(response)


def _limit(response: httpx.Response) -> str:
    """
    Say which limit was hit. The free tier caps requests per minute as well as
    per day, both as 429, and a per-minute block clears in a minute. Calling
    every 429 a spent day sent two people off diagnosing the wrong problem.
    """
    try:
        details = response.json()["error"].get("details") or []
    except Exception:  # noqa: BLE001
        return _message(response)

    quota = [d for d in details if "QuotaFailure" in d.get("@type", "")]
    ids = [v.get("quotaId", "") for d in quota for v in d.get("violations") or []]
    retry = next(
        (d.get("retryDelay") for d in details if "RetryInfo" in d.get("@type", "")), ""
    )
    if any("PerMinute" in i or "per_minute" in i for i in ids):
        return f"Per-minute limit, not the daily one. Wait {retry or 'a minute'} and retry."
    if any("PerDay" in i or "per_day" in i for i in ids):
        return "The daily free-tier limit. It resets at midnight Pacific."
    return _message(response) + (f" Retry in {retry}." if retry else "")


def _message(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["message"])
    except Exception:
        return f"HTTP {response.status_code}."


def _first_json(response: httpx.Response) -> dict[str, Any]:
    # No candidates usually means the response was blocked.
    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise HTTPException(502, "The model returned nothing. It may have been blocked.")
    try:
        text = candidates[0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, ValueError) as error:
        raise HTTPException(502, "The model returned something unreadable.") from error
