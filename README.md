# hired

Paste a job posting, get a tailored one-page CV as a PDF, saved next to the
posting it was made for.

The app never invents a claim. Your experience lives in one master profile: a
fixed pool of bullets, each project with an explicit list of what can and
cannot be claimed. The model picks bullet ids, not prose, and the page is built
from your own sentences after the call. The score, the gaps and which projects
make the page are worked out in code from your profile, so one posting gives
the same answer every time. A guard checks that numbers and qualifiers survive
any rewording.

## What it does

- **Fit check.** Reads the posting, matches every requirement against your
  profile and counts the score from what is met, lists the gaps, and flags
  postings you have already applied to. A model writes only the two or three
  sentences explaining the score.
- **Generate.** Picks the title, summary and bullets that fit the posting, lets
  you swap any of them or regenerate, previews the page and exports a PDF. A
  picker names the model that answers, for comparing two.
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
| Models | granite3.3:8b on your own machine reads the posting and picks title and bullets; Gemini writes the reasons; score, gaps and project ranking are code |
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

Reading a posting and picking bullets are done by a model on your own machine,
through [ollama](https://ollama.com), so there is no quota wall and no third
party choosing the model.

```bash
ollama pull granite3.3:8b      # once, 4.9GB
```

`hired` starts ollama if it is not already running and unloads the model when
you stop. Set `HIRED_OLLAMA_MODEL=` empty in `backend/.env` to turn it off and
use Gemini for everything.

Every call sends an explicit context window, `HIRED_OLLAMA_CTX`, 12288 by
default. Ollama otherwise uses 4096 whatever the model was trained for and drops
the front of anything longer, which cost us a week of believing the model could
not reason: the old one-call prompts ran to 8-9k tokens and arrived with the
profile cut off and the posting intact. Raising it costs memory —
granite3.3:8b is 5.7GB at 4096, 7.1GB at 12288 and 7.8GB at 16384 — so keep it
just above your longest prompt rather than at the model's maximum.

In Docker the app is containerised but ollama is not, because Docker Desktop
has no access to the Mac's GPU and a containerised model would run on the CPU.
Start it yourself with `ollama serve`; compose points the container at
`host.docker.internal` for you.

Why this split. Measured on 8 real postings, counting the technologies each one
names: Gemini found 49% of them, granite3.3:8b found most of the rest, at about
40 seconds a posting against 4. A fit check that silently drops a third of the
requirements produces a confident CV for the wrong job, so the forty seconds
buys something.

Anything the profile can answer is not asked of a model at all:

| Step | Who | Why |
| --- | --- | --- |
| Reading the posting | local first, Gemini fallback | it finds most of the named requirements, and the wait is worth it |
| Score and gaps | code | every requirement is matched against the profile, synonyms and "A or B" included, and the score is counted from what is met. Asked to judge, models reported React missing from a React developer |
| The sentences under the score | Gemini first, local fallback | handed the met and unmet lists, it explains; it cannot move the number |
| Which projects | code | ranked by what each adds to the ones already chosen |
| Title, then bullets per project | local first, Gemini fallback | four small questions instead of one big one. As one call it picked one project of sixteen; asked separately it was right nine times of nine |
| Coverage | code | read off the printed page |

Local calls run at temperature 0, so one posting gives the same score, gaps,
title and bullets every time. The model that read and the model that chose are
stored on the saved application and shown beside the CV.

To compare models, the picker on the Generate screen names one for the fit
check, the CV and Regenerate alike. A named model is binding: it answers or the
call fails, rather than a third model quietly answering. Only models ollama has
pulled, or the configured Gemini, can be named.

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
- [docs/artifacts.md](docs/artifacts.md): the email and the answer, and why a model writes them
- [docs/PROGRESS.md](docs/PROGRESS.md): build log
