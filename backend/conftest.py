"""Test env: outranks .env so no real secrets, keys or hired.db are used."""

import os

import pytest

os.environ["HIRED_SECRET_KEY"] = "test-secret-key"
os.environ["HIRED_DATABASE_URL"] = "sqlite://"
os.environ["HIRED_PASSWORD_HASH"] = ""
# Blank every accepted key spelling so the suite never calls a real provider.
os.environ["HIRED_GEMINI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["HIRED_OPENROUTER_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["OPEN_ROUTER_API_KEY"] = ""


@pytest.fixture(autouse=True)
def _ask_log(tmp_path, monkeypatch):
    """
    Keep the suite out of the real ask log. Without this every fake message in
    every test lands in the file kept for reading back what the model said.
    """
    from app import ask

    monkeypatch.setattr(ask, "LOG", tmp_path / "ask.jsonl")
