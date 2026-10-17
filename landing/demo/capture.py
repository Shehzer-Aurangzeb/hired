# Captures the landing screenshots. Run: cd backend && .venv/bin/python ../landing/demo/capture.py
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "src" / "assets" / "shots"
BACKEND = HERE.parents[1] / "backend"
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"
PASSWORD = "demo-password-for-screenshots"

# Must be set before importing the app, which reads settings at import time.
tmp = Path(tempfile.mkdtemp(prefix="hired-demo-"))
# bin/hired exports this; a script run on its own has to agree with it, or
# Playwright looks in ~/Library/Caches where macOS and cleanup tools delete it.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".playwright"))
os.environ.update(
    HIRED_DATABASE_URL=f"sqlite:///{tmp / 'demo.db'}",
    HIRED_SECRET_KEY="demo-only-not-a-secret",
    HIRED_GEMINI_API_KEY="",
    HIRED_OLLAMA_MODEL="",
)
sys.path.insert(0, str(BACKEND))

from app.auth import hash_password  # noqa: E402

os.environ["HIRED_PASSWORD_HASH"] = hash_password(PASSWORD)

import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app import ask, demo, fit, generate  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402

# One source for the demo data. This file used to carry its own copy, and the
# two drifted the first time either was edited.
JD = demo.JD
fake = lambda prompt, schema, *_, **__: demo.answer(schema, prompt)  # noqa: E731
fit.generate_json = fake
generate.generate_json = fake
ask.generate_json = fake


def serve() -> None:
    init_db()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return
        time.sleep(0.1)
    raise SystemExit("demo server did not start")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    serve()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)

        def shot(name: str, full: bool = False) -> None:
            page.wait_for_load_state("load")
            page.wait_for_timeout(1200)
            page.screenshot(path=OUT / f"{name}.png", full_page=full)
            print("wrote", name)

        page.goto(f"{URL}/login")
        page.fill("#password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url("**/setup")
        shot("setup")

        # In its own thread: seeding prints real PDFs, and a second
        # sync_playwright cannot be opened inside the one this block holds.
        seeding = threading.Thread(target=demo.seed, args=(engine,))
        seeding.start()
        seeding.join()

        page.goto(f"{URL}/generate")
        page.fill("textarea", JD)
        shot("paste")
        page.click("button:has-text('Check fit')")
        page.wait_for_selector("text=Generate a CV")
        shot("fit")

        with page.expect_response("**/api/generate") as generated:
            page.click("button:has-text('Generate a CV')")
        cv = generated.value.json()["cv"]
        page.wait_for_selector("button:has-text('Export')", timeout=60_000)
        page.wait_for_timeout(1500)  # the preview iframe renders after the result
        shot("generate")
        # Same template the PDF prints from, at Letter width (8.5in at 96dpi).
        html = page.request.post(f"{URL}/api/preview", data={"cv": cv}).text()
        sheet = browser.new_page(viewport={"width": 816, "height": 1056}, device_scale_factor=2)
        sheet.set_content(html)
        sheet.add_style_tag(content="html { padding: 0.25in; background: #fff }")  # the PDF margins
        sheet.wait_for_timeout(500)
        sheet.screenshot(path=OUT / "cv.png")
        sheet.close()
        print("wrote cv")

        page.goto(f"{URL}/applications")
        shot("applications")

        page.goto(f"{URL}/profile")
        shot("profile")

        # Ask: a sentence in, a diff waiting on a decision.
        page.goto(f"{URL}/profile?tab=ask")
        page.fill("#ask-input", "I used Redux on Ledgerline and Tidepool, working level")
        page.click("button[aria-label=Send]")
        page.wait_for_selector("text=What would change", timeout=30_000)
        page.wait_for_timeout(600)
        shot("ask")

        # History: versions on the left, what restoring would change on the right.
        page.goto(f"{URL}/profile?tab=history")
        page.wait_for_selector("text=Versions")
        page.click("button:has-text('v1')")
        page.wait_for_selector("text=Restoring v1 would change", timeout=30_000)
        page.wait_for_timeout(600)
        shot("history")

        browser.close()


if __name__ == "__main__":
    main()
