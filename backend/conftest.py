"""Test env: outranks .env so no real secrets, keys or hired.db are used."""

import os

os.environ["HIRED_SECRET_KEY"] = "test-secret-key"
os.environ["HIRED_DATABASE_URL"] = "sqlite://"
os.environ["HIRED_PASSWORD_HASH"] = ""
# Blank every accepted key spelling so the suite never calls a real provider.
os.environ["HIRED_GEMINI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["HIRED_OPENROUTER_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["OPEN_ROUTER_API_KEY"] = ""
