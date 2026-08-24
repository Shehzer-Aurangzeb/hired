"""
Its presence puts backend/ on sys.path so tests can `import app`.

The environment is set here, before any test module imports the app: real
environment variables outrank the .env file, so the suite never depends on a
developer's local secrets and never opens the real hired.db.
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
