"""Calls the LLM: Gemini first, OpenRouter's free pool as fallback.
No retries, only failover, since free tiers are rationed per day."""

import json
from typing import Any

import httpx
from fastapi import HTTPException

from .settings import Settings, get_settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

FREE_POOL = "openrouter/free"

TIMEOUT = 60.0

# Pinned to IPv4: httpx tries IPv6 addresses one by one, and on a network with
# broken IPv6 that took ~64s before falling back. A v4 source address skips them.
_CLIENT = httpx.Client(
    timeout=TIMEOUT,
    transport=httpx.HTTPTransport(local_address="0.0.0.0"),
)


def generate_json(prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Return one JSON object matching `schema`, or raise HTTPException with a readable reason."""
    settings = get_settings()

    if settings.gemini_api_key:
        try:
            return _gemini(prompt, schema, settings)
        except HTTPException:
            # Fall through only if OpenRouter is configured.
            if not settings.openrouter_api_key:
                raise

    if not settings.openrouter_api_key:
        raise HTTPException(503, "No model key is configured on this instance.")
    return _openrouter(prompt, schema, settings)


def _openrouter(prompt: str, schema: dict[str, Any], settings: Settings) -> dict[str, Any]:
    # require_parameters keeps it off models that would ignore the schema.
    # No `strict: true`: it limits which JSON Schema keywords are allowed.
    try:
        response = _CLIENT.post(
            OPENROUTER,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": FREE_POOL,
                "messages": [{"role": "user", "content": prompt}],
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
    try:
        return json.loads(choices[0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        served = body.get("model") or FREE_POOL
        raise HTTPException(502, f"{served} returned something unreadable.") from error


def _gemini(prompt: str, schema: dict[str, Any], settings: Settings) -> dict[str, Any]:
    try:
        response = _CLIENT.post(
            f"{GEMINI}/{settings.gemini_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
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
