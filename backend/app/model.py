"""Calls the LLM: Gemini first, OpenRouter's free pool as fallback.
No retries, only failover, since free tiers are rationed per day."""

import contextvars
import json
from typing import Any

import httpx
from fastapi import HTTPException

from .settings import Settings, get_settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

FREE_POOL = "openrouter/free"

# Which model answered the call in progress. A ContextVar rather than a global
# because sync routes run on a threadpool, and two requests must not see each
# other's answer.
served: contextvars.ContextVar[str] = contextvars.ContextVar("served", default="")

TIMEOUT = 60.0

# Pinned to IPv4: httpx tries IPv6 addresses one by one, and on a network with
# broken IPv6 that took ~64s before falling back. A v4 source address skips them.
_CLIENT = httpx.Client(
    timeout=TIMEOUT,
    transport=httpx.HTTPTransport(local_address="0.0.0.0"),
)


def generate_json(
    prompt: str,
    schema: dict[str, Any],
    turns: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Return one JSON object matching `schema`, or raise HTTPException with a readable reason.

    `turns` is a conversation as (role, text) pairs, role being "user" or "model".
    Sent as real turns rather than a transcript quoted inside `prompt`: a model
    treats what it said itself as its own, and quoted text as background reading.
    """
    settings = get_settings()

    if settings.demo:
        # A demo must not spend a rationed call, and must work with no network.
        from . import demo

        served.set("demo")
        return demo.answer(schema)

    if settings.gemini_api_key:
        try:
            served.set(settings.gemini_model)
            return _gemini(prompt, schema, settings, turns)
        except HTTPException:
            # Fall through only if OpenRouter is configured.
            if not settings.openrouter_api_key:
                raise

    if not settings.openrouter_api_key:
        raise HTTPException(503, "No model key is configured on this instance.")
    served.set(FREE_POOL)
    return _openrouter(prompt, schema, settings, turns)


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


def _openrouter(
    prompt: str,
    schema: dict[str, Any],
    settings: Settings,
    turns: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    # require_parameters keeps it off models that would ignore the schema.
    # No `strict: true`: it limits which JSON Schema keywords are allowed.
    try:
        response = _CLIENT.post(
            OPENROUTER,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": FREE_POOL,
                "messages": [{"role": "user", "content": prompt}]
                + [
                    {"role": turn["role"], "content": turn["text"]}
                    for turn in _turns(turns, "assistant")
                ],
                "provider": {"require_parameters": True},
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "schema": schema},
                },
            },
        )
    except httpx.TimeoutException as error:
        raise HTTPException(504, "The model took too long. Try again.") from error
    except httpx.HTTPError as error:
        raise HTTPException(502, "Could not reach OpenRouter.") from error

    if response.status_code == 429:
        raise HTTPException(
            429,
            "OpenRouter's rate limit is spent. Free models allow 50 requests a day "
            "without credits, and the count resets at UTC midnight.",
        )
    if response.status_code == 402:
        raise HTTPException(402, f"OpenRouter refused on credit. {_message(response)}")
    if response.status_code == 503:
        raise HTTPException(
            502, f"No free OpenRouter model can serve a schema. {_message(response)}"
        )
    if response.status_code >= 400:
        raise HTTPException(502, f"OpenRouter refused the request. {_message(response)}")

    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise HTTPException(502, "OpenRouter returned nothing. It may have been filtered.")
    served.set(body.get("model") or FREE_POOL)
    try:
        return json.loads(choices[0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(502, f"{served.get()} returned something unreadable.") from error


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
        raise HTTPException(
            429, "The model's rate limit is spent. The free tier resets daily."
        )
    if response.status_code == 404:
        # Retired model name; the error body names the replacement.
        raise HTTPException(502, f"{_message(response)} Set HIRED_GEMINI_MODEL.")
    if response.status_code >= 400:
        raise HTTPException(502, f"The model refused the request. {_message(response)}")

    return _first_json(response)


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
