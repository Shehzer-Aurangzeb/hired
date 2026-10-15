# hired

Paste a job posting, get a tailored one-page CV as a PDF, saved next to the
posting it was made for.

The app never invents a claim. Your experience lives in one master profile: a
fixed pool of bullets, each project with an explicit list of what can and
cannot be claimed. The model picks bullet ids, not prose, and the page is built
from your own sentences after the call. A guard checks that numbers and
qualifiers survive any rewording.

## What it does

- **Fit check.** Scores a posting against your profile, lists which
  requirements you cover and which you don't, and flags postings you have
  already applied to.
- **Generate.** Picks the title, summary and bullets that fit the posting, lets
  you swap any of them, previews the page and exports a PDF.
- **Applications.** Every CV you send is saved with its posting. Track status,
  follow-ups, notes and a daily target, and re-download any PDF.
- **Profile.** Edit the master profile as a form, as raw source, or by
  describing the change in a sentence ("add Docker to my skills"). Every save
  is a version, with diffs and one-click restore.

## Stack

| Part | Tech |
| --- | --- |
| `backend/` | FastAPI, SQLModel on SQLite, Jinja + Playwright (Chromium) for the PDF |
| `frontend/` | Angular 20, standalone components, signals, Tailwind 4 |
| `landing/` | Astro, deployed separately on Vercel |
| Models | Gemini for scoring and selection, granite3.3:8b on your own machine for reading the posting |
| Run | `bin/hired` launcher, locally or in Docker |

The profile is Markdown headings around YAML, parsed with `yaml.safe_load`, no
model involved. The grammar is in [docs/parser_contract.md](docs/parser_contract.md)
and a full example in [docs/master_template.md](docs/master_template.md).

## Run it

You need either Docker, or Python 3, Node 20+ and pnpm. The `hired` command
works the same with both: with `backend/.venv` present it runs locally,
otherwise it runs in Docker.

```bash
git clone https://github.com/Shehzer-Aurangzeb/hired && cd hired
ln -s "$PWD/bin/hired" ~/.local/bin/hired   # any folder on your PATH works

hired setup    # creates backend/.env: secret key, password, Gemini key
hired          # builds, starts, opens http://127.0.0.1:8000
```

The first Docker start builds the image (about 1.4GB, a few minutes). Your
data lives in the `hired-data` Docker volume, so it survives rebuilds.

Get a Gemini key from [Google AI Studio](https://aistudio.google.com).

### The local model

Reading a posting is done by a model on your own machine, through
[ollama](https://ollama.com). It is also what answers when Gemini is rate
limited, so there is no quota wall and no third party choosing the model.

```bash
ollama pull granite3.3:8b      # once, 4.9GB
```

`hired` starts ollama if it is not already running and unloads the model when
you stop. Set `HIRED_OLLAMA_MODEL=` empty in `backend/.env` to turn it off and
use Gemini for everything.

In Docker the app is containerised but ollama is not, because Docker Desktop
has no access to the Mac's GPU and a containerised model would run on the CPU.
Start it yourself with `ollama serve`; compose points the container at
`host.docker.internal` for you.

Why this split. Measured on 8 real postings, counting the technologies each one
names: Gemini found 49% of them, granite3.3:8b found most of the rest, at about
40 seconds a posting against 4. A fit check that silently drops a third of the
requirements produces a confident CV for the wrong job, so the forty seconds
buys something.

The local model is used three ways, by how much a wrong answer costs:

| Step | Local model | Why |
| --- | --- | --- |
| Reading the posting | first | it reads better, and the wait is worth it |
| Scoring the fit | never | asked to judge, it reported Azure, open source contributions and authoring GraphQL APIs, none of which are in the profile. When Gemini will not answer, the score is counted in code instead: how many of the things the posting names appear in the profile, clamped to the middle of the scale because counting words cannot earn either extreme |
| Choosing bullets | never | it returned a bullet id as a project and invented a title; a fabricated page is worse than no page |

When a local model answers, its name is shown beside the CV and on the saved
application, so a weaker answer is visible rather than silent.

Before each local call `hired` checks the machine: it declines when the battery
is under 30% and unplugged, when macOS reports thermal throttling, or when less
than 15% of memory is free. A loaded 8B model is about a third of 16GB, so that
floor is what is left beyond it.

```bash
hired stop | restart | status | log | backup | doctor | help
```

It listens on `127.0.0.1` only. `hired doctor` lists anything missing and how
to fix it. `hired backup` copies the database and your profile into
`backend/backups`.

On first run you land on `/setup`: paste an existing profile, upload a file,
or start from the template. The profile is stored in the database, not on disk.

### Without Docker

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd .. && hired setup && hired
```

`hired` installs Chromium and the frontend packages on first run. To force
Docker even with a local setup, use `HIRED_DOCKER=1 hired`.

### Frontend development

```bash
bin/hired dev      # backend on 8000, ng serve on 4200 with a proxy
```

### Landing page

```bash
cd landing && pnpm install && pnpm dev
```

Its screenshots come from an invented profile, never a real one. To refresh
them after a UI change:

```bash
cd backend && .venv/bin/python ../landing/demo/capture.py
```

That builds a throwaway in-memory database, fills it from `backend/app/demo.py`,
and writes `landing/src/assets/shots/`. `bin/hired demo` serves the same data on
port 8001 if you want to click around it. Both need the local setup rather than
Docker, and neither can reach a real database: demo mode refuses to start
against anything but an in-memory one.

## Tests

```bash
cd backend && .venv/bin/python -m pytest
```

## Docs

- [docs/master_template.md](docs/master_template.md): every profile field, with examples
- [docs/master_interview_prompt.md](docs/master_interview_prompt.md): a prompt that interviews you and writes your profile
- [docs/parser_contract.md](docs/parser_contract.md): the profile grammar
- [docs/profile-editing.md](docs/profile-editing.md): how editing by sentence works
- [docs/PROGRESS.md](docs/PROGRESS.md): build log
