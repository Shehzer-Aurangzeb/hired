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
| Models | Gemini, with OpenRouter's free tier as the fallback |
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
`HIRED_OPENROUTER_API_KEY` in `backend/.env` is an optional fallback.

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
