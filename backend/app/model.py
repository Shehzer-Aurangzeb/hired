"""
The one place that talks to a model.

Gemini's REST API is a single POST, so this is httpx rather than an SDK. Both
callers that will exist, the fit check and the selector, want the same thing:
send a prompt, get back JSON matching a schema. Response schemas are enforced by
Google, so "the model returned prose instead of JSON" is not a failure mode we
have to carry.

ponytail: no retry. The free tier is rationed by requests per day, so a retry
spends tomorrow's budget to paper over a blip. Add one when a paid key makes a
failed call cheap.
"""

import json
from typing import Any

import httpx
from fastapi import HTTPException

from .settings import get_settings

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Thinking models take their time, and the fit check is one call a person is
# waiting on rather than a batch job.
TIMEOUT = 60.0


def generate_json(prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    """
    Ask for one JSON object shaped like `schema`, and return it parsed.

    Every failure becomes an HTTPException carrying a sentence a person can act
    on, because "the model call failed" is the same message whether the key is
    missing, the quota is spent, or Google is down, and those need three
    different responses from whoever reads it.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        # Same shape as the auth 503 when no password hash is set: not configured
        # is a setup problem and should not read like the model refused.
        raise HTTPException(503, "No model key is configured on this instance.")

    try:
        response = httpx.post(
            f"{BASE}/{settings.gemini_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                },
            },
            timeout=TIMEOUT,
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
        # Google retires model names and says so in the body, which names the
        # replacement. Passing that through beats "404".
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
    """
    Dig the one JSON payload out of the candidate envelope. A response with no
    candidate at all is usually a safety block, which is worth saying plainly
    rather than surfacing as a KeyError.
    """
    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise HTTPException(502, "The model returned nothing. It may have been blocked.")
    try:
        text = candidates[0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, ValueError) as error:
        raise HTTPException(502, "The model returned something unreadable.") from error
