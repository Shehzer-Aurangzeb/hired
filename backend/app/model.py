"""Calls a model: Gemini over the network, granite on this machine.
No retries, only failover, since free tiers are rationed per day."""

import contextvars
import json
import re
import subprocess
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import HTTPException

from .settings import Settings, get_settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"


# Which model answered the call in progress. A ContextVar rather than a global
# because sync routes run on a threadpool, and two requests must not see each
# other's answer.
served: contextvars.ContextVar[str] = contextvars.ContextVar("served", default="")

# Set when an answer came back schema-valid but useless and had to be asked for
# again, so the screen can say so instead of the retry being invisible.
notice: contextvars.ContextVar[str] = contextvars.ContextVar("notice", default="")

# The model the screen asked for, or "" for the configured routing. A request
# scoped variable rather than a parameter because six call sites across three
# modules would otherwise have to thread it through, and none of them choose it.
pick: contextvars.ContextVar[str] = contextvars.ContextVar("pick", default="")


def available(settings: Settings) -> list[str]:
    """The models this machine can answer with, pulled ones first."""
    local: list[str] = []
    if settings.ollama_model:
        try:
            tags = _LOCAL.get(f"{settings.ollama_url}/api/tags", timeout=5).json()
            local = sorted(m["name"] for m in tags.get("models") or [])
        except Exception:  # noqa: BLE001 — ollama being down is not an error here
            local = [settings.ollama_model]
    return local + ([settings.gemini_model] if settings.gemini_api_key else [])


def choose(name: str) -> None:
    """Honour a named model for this request, or fall back to the routing.

    Checked rather than trusted: the name is handed to ollama, and a request
    body is not the place to decide what this machine runs.
    """
    name = (name or "").strip()
    if name and name not in available(get_settings()):
        raise HTTPException(422, f"No model called {name} is available here.")
    pick.set(name)

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
    local: str = "never",
    good: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """
    Return one JSON object matching `schema`, or raise HTTPException with a readable reason.

    `turns` is a conversation as (role, text) pairs, role being "user" or "model".
    Sent as real turns rather than a transcript quoted inside `prompt`: a model
    treats what it said itself as its own, and quoted text as background reading.

    `local` says how the model on this machine may be used:

      "first"     ask it before Gemini. Reading a posting: it finds most of the
                  named requirements against Gemini's half, and the extra half
                  minute buys something.
      "fallback"  ask it only when Gemini will not answer. Scoring: slower and
                  plainer, but given the whole profile it names real gaps and
                  invents nothing, and a daily quota that runs out at noon is
                  not an answer. The answer carries the model's name.
      "only"      that model or an error. Set when the screen names one, so a
                  comparison between models is not quietly answered by a third.
      "never"     Gemini or an error. Choosing bullets: the local model picks
                  only real ids, but across three runs of one posting it chose
                  a different title each time, and a page assembled from a
                  shuffle is worse than no page.

    `good` decides whether an answer is worth returning. A schema keeps the
    shape, not the substance: a posting once came back with zero requirements in
    it, which is valid JSON and not an answer, and every later step ran against
    an empty list without complaining. A false verdict buys one more attempt and
    sets `notice`.
    """
    settings = get_settings()
    notice.set("")
    # A chosen model is binding: no silent failover, because an answer from a
    # model you did not choose makes the comparison you chose it for worthless.
    chosen = pick.get()
    if chosen and chosen != settings.gemini_model:
        settings = settings.model_copy(update={"ollama_model": chosen})
        local = "only"

    if settings.demo:
        # A demo must not spend a rationed call, and must work with no network.
        from . import demo

        served.set("demo")
        return demo.answer(schema)

    def gemini() -> dict[str, Any]:
        served.set(settings.gemini_model)
        return _gemini(prompt, schema, settings, turns)

    def run_local() -> dict[str, Any]:
        served.set(settings.ollama_model)
        return _ollama(prompt, schema, settings, turns)

    usable_local = local != "never" and bool(settings.ollama_model)

    def attempt() -> dict[str, Any]:
        if local == "only":
            return run_local()
        if chosen:  # the configured Gemini model, chosen by name
            return gemini()
        if local == "first" and usable_local:
            try:
                return run_local()
            except HTTPException:
                if not settings.gemini_api_key:
                    raise

        if not settings.gemini_api_key:
            if usable_local:
                return run_local()
            raise HTTPException(503, "No model is configured on this instance.")

        try:
            return gemini()
        except HTTPException:
            if local == "fallback" and usable_local:
                return run_local()
            raise

    answer = attempt()
    if good is None or good(answer):
        return answer

    # ponytail: one retry, not a loop. A model that empties twice on the same
    # prompt is not going to fill it on the third ask, and the wait is a minute.
    notice.set("The model came back with nothing usable, so it was asked again.")
    answer = attempt()
    if good(answer):
        return answer
    raise HTTPException(
        502, f"{served.get()} returned an empty answer twice. Try again in a moment."
    )


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
        # num_ctx: without it ollama uses 4096 and truncates from the front, so
        # a long prompt loses its briefing and keeps its tail.
        # temperature: ollama defaults to 0.8. Reading one posting three times
        # gave 15, 18 and 23 requirements, and the gaps moved with them. At 0 it
        # gave 20 three times. A seed and top_k on top changed nothing measured,
        # because decoding at 0 is already greedy.
        "options": {"num_ctx": settings.ollama_ctx, "temperature": 0},
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
                    # Same reason as the local call: the same posting read twice
                    # should give the same requirements.
                    "temperature": 0,
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
