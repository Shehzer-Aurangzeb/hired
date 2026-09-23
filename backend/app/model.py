"""
The one place that talks to a model. Gemini first because it answers fast, with
OpenRouter's free pool behind it for when Gemini is loaded or out of quota.

ponytail: no retry, only failover. The free tiers are rationed per day, so a
retry spends tomorrow's budget on a blip.
"""

import json
from typing import Any

import httpx
from fastapi import HTTPException

from .settings import Settings, get_settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

# OpenRouter routes this across whatever free models are currently up.
FREE_POOL = "openrouter/free"

# Thinking models take their time, and the fit check is one call a person is
# waiting on rather than a batch job.
TIMEOUT = 60.0

# One client, pinned to IPv4. Both providers resolve to a long list of IPv6
# addresses first, and on a network whose IPv6 is blackholed every one of them
# has to time out before Python falls back: measured at 64s to Google against
# 0.2s over IPv4. curl hides this by racing both families (RFC 8305); httpx
# walks them in order, and the connect timeout is per address, so it cannot
# help. Binding a v4 source address makes getaddrinfo skip the v6 records.
_CLIENT = httpx.Client(
    timeout=TIMEOUT,
    transport=httpx.HTTPTransport(local_address="0.0.0.0"),
)


def generate_json(prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    """
    One JSON object shaped like `schema`. Failures carry a sentence, because a
    missing key and a spent quota need different answers.
    """
    settings = get_settings()

    if settings.gemini_api_key:
        try:
            return _gemini(prompt, schema, settings)
        except HTTPException:
            # Only swallowed when there is somewhere else to go.
            if not settings.openrouter_api_key:
                raise

    if not settings.openrouter_api_key:
        # Not configured is a setup problem, and should not read like a refusal.
        raise HTTPException(503, "No model key is configured on this instance.")
    return _openrouter(prompt, schema, settings)


def _openrouter(prompt: str, schema: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """
    The fallback. OpenRouter's free pool, so a dead model is its problem, and
    require_parameters keeps it off endpoints that would ignore the schema. The
    free models think for a while, which is why this is second and not first.

    ponytail: no `strict: true`, which restricts the JSON Schema keywords and
    would mean rewriting both schemas to suit one provider.
    """
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
    """Google AI Studio, which enforces the schema server-side."""
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
        # Google retires model names and names the replacement in the body.
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
    """Dig the JSON out of Gemini's envelope. No candidate is usually a block."""
    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise HTTPException(502, "The model returned nothing. It may have been blocked.")
    try:
        text = candidates[0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, ValueError) as error:
        raise HTTPException(502, "The model returned something unreadable.") from error
