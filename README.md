# hired

Paste a job description, get a tailored one-page CV PDF, saved alongside the
posting that produced it.

The generator never invents a claim. It selects from a fixed pool of bullets in
a hand-written master profile, each project carrying an explicit list of what
can and cannot be claimed. The model returns bullet ids, not prose, and a
validation layer checks that numbers and qualifiers survive any rephrasing.

Angular front-end, FastAPI back-end, Claude for parsing and selection,
Playwright for the PDF.

## Layout

```
backend/     FastAPI, profile parser, claim guard, renderer, SQLite
frontend/    Angular 20, standalone components, signals, Tailwind
docs/        PROGRESS.md, written after each phase
BUILD_PLAN.md
```

One repo, two apps, no workspace tool. They share nothing at build time and
have separate package managers, so a build graph would be overhead with no
payoff.

## Run

```bash
# backend, port 8000
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload

# frontend, port 4200
cd frontend
npm install
npm start
```

Until `backend/profile/master.md` exists, point the backend at the fixture:

```bash
HIRED_MASTER=tests/fixtures/master.md .venv/bin/uvicorn app.main:app --reload
```

## Test

```bash
cd backend && .venv/bin/python -m pytest
```

## State

See [docs/PROGRESS.md](docs/PROGRESS.md). Phase 1 and the v1 frontend are done.
The generate, export and applications endpoints are still mocked in the browser;
flip `USE_MOCKS` in `frontend/src/app/core/api.ts` as each one lands.
