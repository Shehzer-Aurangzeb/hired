# hired

Paste a job description, get a tailored one-page CV PDF, saved alongside the
posting that produced it.

The generator never invents a claim. It selects from a fixed pool of bullets in
a hand-written master profile, each project carrying an explicit list of what
can and cannot be claimed. The model returns bullet ids, not prose, and a
validation layer checks that numbers and qualifiers survive any rephrasing.

Angular front-end, FastAPI back-end, Gemini for the fit check and the
selector, Playwright for the PDF.

**Claude does not parse the profile.** The master file is markdown headings
wrapping YAML, and the parser is a heading split plus `yaml.safe_load`. That
is a deliberate choice, not a stopgap. The claim guard's whole job is checking
generated output against the boundaries in the file, and a guard whose input was
also produced by a model is checking Claude against Claude. The grammar is in
[docs/parser_contract.md](docs/parser_contract.md).

**The selector returns bullet ids, never prose.** A model that can only point at
existing sentences cannot write a new one, and the page is assembled from the
profile after the call. Every other honesty mechanism here is a policy a model
could break; that one it cannot.

## Layout

```
backend/     FastAPI, profile parser, SQLite
frontend/    Angular 20, standalone components, signals, Tailwind
docs/        PROGRESS.md, the parser contract, the profile template
             and the Claude briefing
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

Copy `backend/.env.example` to `backend/.env` first: `HIRED_SECRET_KEY` has no
default and the app will not start without it, `HIRED_PASSWORD_HASH` comes from
`.venv/bin/python -m app.hash_password`, and `HIRED_GEMINI_API_KEY` is what the
fit check and the selector run on. Then `.venv/bin/playwright install chromium`,
which is the browser that prints the PDF.

The profile lives in the database, not on disk: one row, written through the
setup screen or the Profile tab, because a container filesystem is wiped on
redeploy and that row is the only copy of the CV data. First run sends you to
`/setup`, which offers a paste, a file, or the starter template.

## Test

```bash
cd backend && .venv/bin/python -m pytest
```

## State

See [docs/PROGRESS.md](docs/PROGRESS.md).

**Nothing is mocked.** Every route is live: auth, the profile, the fit check,
the selector and its claim guard, the PDF export, applications.

Remaining: a real `master.md` written against
[docs/master_template.md](docs/master_template.md), and a deploy target.
