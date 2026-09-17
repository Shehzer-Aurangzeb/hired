"""
Puts backend/ on sys.path so tests can `import app`, and sets the environment
before any test imports it. Real environment variables outrank .env, so the
suite never reads a developer's secrets or opens the real hired.db.
"""

import os

os.environ["HIRED_SECRET_KEY"] = "test-secret-key"
os.environ["HIRED_DATABASE_URL"] = "sqlite://"
os.environ["HIRED_PASSWORD_HASH"] = ""
# Both spellings, because the setting accepts both. Without this the suite makes
# real, rate-limited calls to Google against whatever key is in .env: the first
# run of test_fit.py did exactly that before this line existed.
os.environ["HIRED_GEMINI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
# Same for the other provider, and for the same reason. Every accepted spelling
# has to be blanked: one live key left readable is a suite that quietly burns a
# rationed daily allowance every time it runs.
os.environ["HIRED_OPENROUTER_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["OPEN_ROUTER_API_KEY"] = ""
