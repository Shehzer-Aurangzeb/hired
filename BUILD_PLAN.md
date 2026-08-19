# hired — Build Plan

Angular frontend, Python FastAPI backend. A personal tool that turns a pasted job description into a tailored one-page CV PDF, generated from a master profile file, with every claim bounded by what I can actually defend in an interview.

Companion to Outreach Deck. Outreach Deck handles networking. hired handles applying.

**Name is always lowercase**, in the logo, the README, the UI, and the package name. Repo `hired`, package `hired`, app title `hired`.

---

## How to build this with Claude Code

This plan is phase-gated on purpose. Work one phase at a time, in order. Do not let the agent run ahead into the next phase.

Put this file at the repo root as `BUILD_PLAN.md` and start each session with:

> Read BUILD_PLAN.md. We are on Phase N. Build only Phase N. Stop when the exit criteria for Phase N are met and tell me what you did. Do not start Phase N+1.

Rules to hold the agent to across every phase:

- Never edit `profile/master.md`. It is hand-written and is the source of truth.
- Never weaken or bypass the claim guard to make a test pass.
- Every model call is server-side. The API key never reaches Angular.
- No em dash in any generated string, any UI copy, or any committed file.
- Ask before adding a dependency that is not already named in this plan.
- After each phase, write what changed to `docs/PROGRESS.md` so the next session has context.

Read the phase exit criteria yourself before accepting the work. The whole value of this tool is that it does not overclaim, and a phase that looks done but skipped the guard is worse than no tool at all.

| Phase | What it delivers | Exit criteria |
|---|---|---|
| 0 | `profile/master.md` | Every project has a claim boundary written before its bullet text. Hand-written, no agent. |
| 1 | FastAPI skeleton, profile parser, `GET /api/profile` | Parser returns the full profile as JSON, pytest passes on the parser. |
| 2 | Jinja template, Playwright PDF export | PDF from hardcoded JSON is visually identical to the current CV. No AI involved yet. |
| 3 | One-page render-and-measure loop | Deliberately overstuffed input converges to one page, never drops a project's last bullet without dropping the project. |
| 4 | Claim guard, pytest | Failing cases written first: em dash, banned word, altered number, blocked bullet, gated skill without evidence. |
| 5 | Claude JD parser | Three real saved JDs parse into correct structured output. |
| 6 | Claude selector | Returns bullet ids only. Full pipeline works from a curl command. |
| 7 | Angular shell, routing, generate page | Paste a JD in the browser, see a fit score and selected bullets. |
| 8 | Bullet selector, drag-drop, live preview | Reorder and deselect bullets, preview matches the printed PDF. |
| 9 | Save and list applications | One real application generated, exported, and saved end to end. |

Phases 10 and beyond are v2 and do not start until twenty real applications have gone through the tool.

---

## Why this exists

The bottleneck is not writing bullets. It is the loop: open the old PDF, edit bullets by hand, fix the formatting that broke, export, name the file something, lose track of which version went where. Two folders of resumes and no idea which is which. That loop is what kills the motivation to apply, and applying is a daily activity.

hired removes the loop. Paste JD, get a correctly formatted one-page PDF, saved alongside the JD that produced it.

Secondary purpose, equally real: Angular and FastAPI are both gaps that have cost me opportunities. Building a tool I open every day in two unfamiliar frameworks beats a tutorial project I abandon. When an interviewer asks about Angular, the answer becomes "I built and use a tool in it."

---

## The rule that shapes everything

**The generator never invents a claim. It selects, reorders, and lightly rephrases inside a per-project claim boundary.**

Every project in the master file carries an explicit list of what can be claimed and what cannot. If a JD asks for something that sits outside the boundary, the generator does not stretch a bullet to cover it. It surfaces the gap to me and leaves the bullet alone.

This is what keeps "~50% API call reduction" labeled estimated, keeps Stanley Paden in-app purchases off the page until package.json is confirmed, keeps Skyflow as consumed rather than built, and keeps Dedicate as an asset management platform rather than an investment platform.

Not a v2 feature. In from the first commit, enforced in code, not just in the prompt.

---

# Phase 0: The master profile file

**Blocking prerequisite. Nothing downstream is worth anything until this exists.** Do this before touching Angular.

Format: a single Markdown file, `profile/master.md`, parsed once at startup into structured objects. Markdown because I edit it by hand constantly and JSON is miserable to hand-edit. Parsing is a small deterministic parser, not an AI call.

## File structure

```markdown
# Identity
name: Shehzar Aurangzeb Abbasi
location: Montreal, QC
relocation: Open to relocation
email: shehzerabbasi621@gmail.com
phone: +1 514 241 1019
linkedin: linkedin.com/in/shehzar-aurangzeb-70009520b
portfolio: shehzaraurangzeb.com
github: github.com/Shehzer-Aurangzeb
authorization: Authorized to work in Canada, no sponsorship required

# Titles
- id: fullstack
  text: Full-Stack Engineer | React · Next.js · TypeScript · Node.js
- id: frontend
  text: Front-End Engineer | React · TypeScript · Next.js · Design Systems
- id: mobile
  text: Mobile Engineer | React Native · Expo · TypeScript

# Summaries
- id: fullstack
  max_chars: 520
  text: >
    Full-stack engineer with 3.5+ years in TypeScript across the front-end and
    back-end...
- id: frontend
  ...

# Skills
- line: Frontend
  items: [React, Next.js, TypeScript, JavaScript, Tailwind, TanStack Query, ...]
  never_standalone: []
- line: Backend
  items: [NestJS, Node.js, PostgreSQL, Prisma, REST, GraphQL, JWT, Auth0]
- line: Mobile
  items: [React Native, Expo, EAS Build/Update/Submit]
- line: AI Tooling
  items: [Claude Code, Cursor, Claude API, agent design]
- line: Infra
  items: [Docker, GitHub Actions, Vercel, Render, AWS]
  gated: [AWS]        # only include when evidence project is on the page

# Experience
## Devnito
role: Frontend & Mobile Engineer
location: Remote
start: 2024-11
end: present
priority: 1

### Dedicate
label: VC-backed asset management platform
stack: [Next.js, React, TypeScript, TanStack Query, Auth0]
priority: 1
tags: [frontend, react, nextjs, typescript, auth, caching, design-system, testing]

claim_boundary:
  can_claim:
    - Built the front-end from scratch, front-end lead on a team of ~10
    - BFF pattern, service credentials stay server-side
    - Auth0 integration, HttpOnly session cookies, passwordless OTP, passkey support
    - Consumed a multi-IDP token chain feeding Skyflow for privileged API calls
    - TanStack Query data layer, tiered caching across hot/warm/cold data, 18 query patterns
    - Vitest unit tests covering API route handlers
    - Adaptive layouts via a useBreakpoint hook, separate component trees per breakpoint
    - Component registry built from scratch with variants rendered on screen
    - Accessibility: ARIA labels on interactive elements, full keyboard navigation
  cannot_claim:
    - Built Skyflow, or built the vault. Consumed only.
    - Product direction. I build UI for backend features, I do not make product calls.
    - Storybook on this project. Component registry is from scratch.
    - Measured performance numbers. The ~50% figure is estimated.
  required_qualifiers:
    - "~50% reduction in repeat API calls" must always carry the word "estimated"

bullets:
  - id: dedicate-frontend-scratch
    priority: 1
    tags: [frontend, react, nextjs, ownership]
    text: Built the front-end from scratch in Next.js and TypeScript on a BFF pattern...
  - id: dedicate-auth
    priority: 2
    tags: [auth, security]
    text: Set up the full authentication system: Auth0 with HttpOnly session cookies...
  - id: dedicate-caching
    priority: 2
    tags: [performance, data-layer, caching]
    text: Built the data layer with TanStack Query and tiered caching across 18 query
          patterns, cutting repeat API calls by an estimated 50%...
  ...
```

Repeat that block for: Hospital Management System, Union AI, Stanley Paden, RUNIQ, ConceptZI (RATP Dev USA, GData Labs, GraphQL work), Swift Reflex, Outreach Deck, hired, Meridian.

## Rules baked into the file

Carry these as machine-readable constraints, not as prose I hope the model reads:

| Constraint | Enforcement |
|---|---|
| Dedicate is an asset management platform | `label` field is fixed, never generated |
| ~50% is estimated | `required_qualifiers` on the bullet |
| Stanley Paden IAP unverified | bullet exists with `status: blocked`, excluded from selection |
| AWS only when evidence is on the page | `gated` skill, included only if Meridian bullet selected |
| No permit expiry anywhere | not present in the identity block at all |
| PHP never a standalone skill item | absent from every skills line, present only in Swift Reflex bullets |
| Swift Reflex is unpaid family work | `disclosure` field, surfaced in the UI as an interview reminder |
| No em dashes | validator rejects `—` in any generated string |
| No first person in bullets | validator rejects leading pronouns, all bullets verb-first |
| HMS requirements came through Devnito | `cannot_claim: direct clinic contact` |
| Built from scratch, not architected | banned word list includes "architected" |

## Deliverable for Phase 0

`profile/master.md` complete for every project, with claim boundaries written before any bullet text. Estimate: one focused session. This is writing, not coding, and it is the highest-leverage part of the whole build.

---

# v1

**Scope:** paste JD → fit score → tailored one-page CV → PDF → saved record.

Nothing else. No auth, no multi-user, no cloud, no cover letters, no dashboard.

## v1 user flow

1. Open the app at `localhost:4200`.
2. Paste a JD into a textarea. Optionally type company and role, or let the extractor pull them.
3. Hit Generate.
4. See a fit score out of 10, two lines of reasoning, and a list of gaps.
5. See the selected bullets grouped by project, each with a checkbox and a drag handle.
6. See any claim boundary flags: "JD asks for Kubernetes, no bullet covers it, not adding one."
7. Adjust selection if I want. Regenerate the summary if I want.
8. Hit Export. Get a one-page PDF with a deterministic filename.
9. The JD, the fit score, the selected bullet ids, and the PDF path save as one record.

## Backend: FastAPI

### Layout

```
backend/
  app/
    main.py                 # FastAPI app, CORS for localhost:4200, router mounting
    config.py               # pydantic-settings, reads .env
    api/
      routes/
        profile.py
        generate.py
        applications.py
        export.py
      deps.py               # dependency injection: profile store, claude client, db session
    core/
      profile_parser.py     # master.md -> Profile object
      claim_guard.py        # validation layer, the enforcement code
      one_page.py           # render-and-measure loop
      filenames.py          # deterministic naming
    services/
      claude_client.py      # single place that talks to Anthropic
      jd_parser.py          # JD -> structured requirements
      selector.py           # requirements + profile -> selected bullets + score
      renderer.py           # structured CV -> HTML -> PDF via Playwright
    models/
      profile.py            # Pydantic: Profile, Experience, Project, Bullet, ClaimBoundary
      jd.py                 # ParsedJD, Requirement
      cv.py                 # GeneratedCV, SelectedBullet, FitScore
      application.py        # SQLModel table
    templates/
      cv.html               # Jinja2, fixed layout, matches current CV exactly
      cv.css
    db.py                   # SQLModel engine, SQLite
  storage/
    applications.db
    output/                 # generated PDFs
    jds/                    # raw JD text, one file per application
  profile/
    master.md
  tests/
```

### Why these choices

- **SQLModel over raw SQLAlchemy.** It is Pydantic and ORM in one class, which halves the amount of unfamiliar Python I need to hold in my head.
- **SQLite, one file, no server.** Migrating to Postgres later is a connection string change.
- **Jinja2 for the CV template.** Server-rendered HTML, then Playwright prints it. Angular never renders the PDF.
- **pydantic-settings for config.** Standard FastAPI pattern, worth learning properly.

### Endpoints

```
GET  /api/profile
     -> parsed master.md as JSON. Used by the frontend to show what is available.

POST /api/profile/reload
     -> re-parse master.md from disk. Called after I edit the file.

POST /api/generate
     body: { jd_text, company?, role?, title_variant? }
     -> {
          parsed_jd: { company, role, required[], preferred[], keywords[] },
          fit: { score: 0-10, reasoning: str, gaps: [str] },
          cv: {
            title, summary, skills_lines[],
            sections: [ { project_id, label, stack, bullets: [{id, text, source_id}] } ]
          },
          flags: [ { type, message } ]
        }

POST /api/generate/summary
     body: { jd_text, title_variant }
     -> { summary }         # regenerate just the summary without redoing selection

POST /api/export
     body: { application_draft }   # the edited cv object
     -> { pdf_path, filename, page_count }

GET  /api/applications
GET  /api/applications/{id}
POST /api/applications      # save the record after export
GET  /api/applications/{id}/pdf   # FileResponse
```

### The generation pipeline, step by step

**Step 1: parse the JD.** One Claude call, JSON only.

```
Input:  raw JD text
Output: {
  company, role, seniority, location, work_mode,
  required_skills: [{name, importance: 1-3}],
  preferred_skills: [...],
  keywords: [...],           # exact ATS phrasing for later matching
  french_required: bool,
  years_required: int|null
}
```

Deterministic, low temperature. Nothing about me enters this call.

**Step 2: select bullets.** Second Claude call. This is the one that matters.

Input to the model:
- The parsed requirements from step 1.
- The full bullet pool, each with `id`, `text`, `tags`, `priority`, and its project's claim boundary.
- A hard content budget: max 3 bullets per project, max 5 projects, summary under 520 characters.

The model returns **bullet ids only**, plus ordering, plus the fit score:

```json
{
  "title_variant": "fullstack",
  "summary": "...",
  "skills_lines": [{"line": "Frontend", "items": ["React", "..."]}],
  "sections": [
    {"project_id": "dedicate", "bullet_ids": ["dedicate-frontend-scratch", "dedicate-caching"]}
  ],
  "fit": {"score": 8, "reasoning": "...", "gaps": ["Kubernetes", "Go"]},
  "requested_claims_outside_boundary": [
    {"project_id": "dedicate", "requested": "infrastructure ownership", "reason": "JD asks for IaC"}
  ]
}
```

Returning ids rather than text is the structural protection. The model cannot invent a bullet because it can only point at one that already exists.

**Step 3: light rephrase, optional and bounded.** For each selected bullet, one call may adjust wording toward JD keywords. Constraints passed in: keep every number identical, keep every qualifier, stay inside the claim boundary, verb-first, no first person, no em dashes. Output goes straight into the claim guard.

Skip this entirely in the first working version. Add it once selection is solid.

**Step 4: claim guard.** Pure Python, no AI. Runs on every generated string before it reaches the template.

```python
def validate(generated: GeneratedCV, profile: Profile) -> list[Flag]:
    # every bullet id exists in the pool
    # rephrased text preserves all numeric tokens from the source bullet
    # required_qualifiers present (e.g. "estimated" near the 50% figure)
    # no banned words: architected, spearheaded, leveraged
    # no em dash anywhere
    # no first-person pronoun starting any bullet
    # no blocked-status bullet selected (Stanley Paden IAP)
    # gated skills only present when their evidence project is included
    # PHP absent from all skills lines
```

Hard failures raise and block export. Soft flags surface in the UI. This is where the honesty rules live, and it is testable, which makes it the natural place to write real pytest coverage.

**Step 5: render and enforce one page.**

```python
def render_one_page(cv: GeneratedCV) -> Path:
    for attempt in range(8):
        html = jinja.render("cv.html", cv=cv)
        pdf, pages = playwright_print(html)
        if pages == 1:
            return pdf
        cv = drop_lowest_priority_bullet(cv)
    raise CannotFitError(...)
```

`drop_lowest_priority_bullet` uses the bullet `priority` field and never drops a project's last bullet, it drops the whole project instead once it is down to one. Deterministic, roughly fifteen lines, no model involvement.

Playwright specifics: `page.set_content(html)`, `page.emulate_media(media="print")`, `page.pdf(format="Letter", margin=0.5in, print_background=True)`. Chromium headless. This is browser automation, not testing, and that is how I describe it in interviews.

**Step 6: save the record.**

```
Shehzar_Abbasi_AirCanada_FrontEndDeveloper_2026-08-16.pdf
```

Slugged company, slugged role, ISO date. Collision suffix `_2` if it exists. Stored with the JD text, the parsed requirements, the fit score, the selected bullet ids, and the PDF path in one row. When Air Canada calls in three weeks I open the record and see exactly what they read.

### Application table

```python
class Application(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company: str
    role: str
    source: str | None            # LinkedIn, company site, recruiter name
    jd_text: str
    jd_parsed: dict = Field(sa_column=Column(JSON))
    fit_score: int
    fit_reasoning: str
    gaps: list[str] = Field(sa_column=Column(JSON))
    title_variant: str
    selected_bullet_ids: list[str] = Field(sa_column=Column(JSON))
    summary_text: str
    pdf_path: str
    filename: str
    status: str = "generated"     # generated | applied | replied | interview | rejected | offer
    applied_at: datetime | None
    created_at: datetime
    notes: str | None
```

Status transitions are v2 territory, but the column ships in v1 so no migration is needed later.

## Frontend: Angular

Angular 18+, standalone components, signals. No NgModules. This is the current idiom and learning the old module system would be learning something already on its way out.

### Layout

```
frontend/src/app/
  app.config.ts               # provideHttpClient, provideRouter
  app.routes.ts
  core/
    api/
      profile.service.ts
      generate.service.ts
      applications.service.ts
    models/                   # TS interfaces mirroring the Pydantic models
    interceptors/
      error.interceptor.ts
  features/
    generate/
      generate-page.component.ts
      jd-input/
      fit-score-card/
      bullet-selector/
      flags-panel/
      cv-preview/
    applications/
      applications-page.component.ts
      application-detail.component.ts
  shared/
    ui/                       # button, card, badge, spinner
  styles/
    tokens.css
```

### Angular concepts this build forces me to actually learn

| Concept | Where it shows up |
|---|---|
| Standalone components and `imports` array | every component |
| Signals, `computed`, `effect` | selected bullet state, live character counts |
| `HttpClient` and RxJS observables | the three API services |
| `toSignal` / `toObservable` interop | bridging HttpClient into signal state |
| Reactive forms, `FormBuilder`, validators | the JD input form, company and role fields |
| Routing and route params | `/generate`, `/applications`, `/applications/:id` |
| Dependency injection, `inject()` | services into components |
| `@if` / `@for` control flow | replaces `*ngIf` and `*ngFor`, current syntax |
| Interceptors | error handling and loading state |
| CDK drag-drop | bullet reordering |

That table is the study list for after the vibe-coding pass. Working through those ten items with the real code in front of me is the honest version of "I know Angular."

### Key screen: the generate page

Three panes.

- **Left:** JD textarea, company and role inputs, title variant selector, Generate button.
- **Middle:** fit score card at top (number, two lines of reasoning, gap chips), then bullets grouped by project. Each bullet has a checkbox, a drag handle, and a small badge if it was rephrased. Live page-estimate indicator.
- **Right:** live CV preview rendered as HTML in an iframe using the same Jinja template output, so what I see is what prints. Export button underneath.

The flags panel sits above the bullets and is impossible to miss. Red for hard blocks, amber for "JD asks for X, nothing covers it."

## v1 build order

Build in this order specifically so there is something usable at the end of each step.

1. **`master.md` written in full.** No code. Blocking.
2. **FastAPI skeleton + profile parser + `GET /api/profile`.** Verify the file parses into the right shape. Pytest on the parser.
3. **Jinja template + Playwright export, fed by hardcoded JSON.** Get a PDF that is pixel-identical to the current CV before any AI is involved. This is the hardest formatting work and doing it early prevents the whole thing sitting on a broken foundation.
4. **One-page loop.** Feed it deliberately overstuffed input, confirm it drops bullets and converges.
5. **Claim guard + pytest.** Write the failing cases first: em dash present, "architected" present, number altered, blocked bullet selected.
6. **Claude JD parser.** JSON only, tested against three real JDs I have saved.
7. **Claude selector.** Ids only. Wire into guard and renderer. **At this point the tool works from a curl command.**
8. **Angular shell, routing, one service, the generate page.** Wire to the working backend.
9. **Bullet selector with checkboxes and drag-drop, live preview.**
10. **Save and list applications.**
11. **Use it for a real application.** Fix whatever breaks.

Realistic estimate: three days gets steps 1 through 7 plus a rough Angular shell. A week gets a tool I use daily. Three days to a polished full build is not honest, and the earlier scoping conversation already established that.

## v1 explicitly out of scope

Auth, multi-user, deployment, cover letters, LinkedIn scraping, JD-from-URL fetching, email integration, the skills dashboard, status tracking UI.

---

# v2

Only start v2 after twenty-plus real applications have gone through v1. The dashboard needs volume before it says anything, and ten applications is noise.

## Feature 1: Skills frequency dashboard

The feature I actually want, and the reason for saving `jd_parsed` on every record from day one.

**What it computes**

Every JD parsed in v1 already produced a normalized skill list. Aggregate across all of them.

- **Demand:** how many of my last N JDs required each skill, split required vs preferred, weighted by importance.
- **My level:** a self-rated 1 to 10 per skill, stored in `master.md`, plus an evidence count of how many bullets carry that tag.
- **Gap score:** `demand_frequency × (10 - my_level)`. Sorts what to learn next by actual market pull rather than by what feels urgent.

Concretely, if Angular appears in 8 of 10 JDs and my level is 3, it outranks Kubernetes at 4 of 10 and level 2. That is the signal. It is exactly the reasoning that put Angular in this project's stack, formalized.

**Normalization matters more than the math.** "ReactJS", "React.js", and "React" are one skill. Maintain a synonym map in `profile/skills_taxonomy.md` and normalize at parse time, not at display time.

**Views**
- Ranked table: skill, demand count, demand %, my level, gap score, evidence bullets.
- Trend over time, monthly buckets, so a rising skill is visible before it is everywhere.
- Filter by role title, by seniority, by city. "What does Montreal ask for that Toronto does not."
- A single "learn next" callout, top three by gap score.

**Backend:** `GET /api/insights/skills?since=&role=&location=`. Pure SQL aggregation over the JSON column, no AI call. Add a materialized cache only if it gets slow, which at a few hundred rows it will not.

**Frontend:** new `insights` feature area. A chart library is needed here. ngx-charts or a thin ECharts wrapper. This is where I learn Angular's async data patterns properly.

## Feature 2: Application pipeline

Turns the saved records into an actual tracker.

- Kanban or table with the status column already shipped in v1: Generated, Applied, Replied, Interview, Rejected, Offer.
- Timeline per application: applied date, first reply date, days to reply.
- Per-application detail view showing the exact CV sent, the JD, the fit score, and the gaps. This is interview prep, and it is the thing that makes the tool valuable months after the application.
- Follow-up reminder: flag applications sitting in Applied for more than 10 days.
- Notes field per application, for recruiter names and call outcomes.

**Deliberate boundary:** this is a tracker for applications only. Outreach Deck owns people and conversations. Do not rebuild contact management here. The two tools link by company name if anything, and even that can wait.

## Feature 3: CV performance signal

The reason for tracking status honestly.

- Reply rate by fit score band. Does applying below a 6 ever work.
- Reply rate by title variant. Does the front-end framing beat the full-stack framing.
- Which bullets appear most often in applications that got replies. Weak signal at low volume, labeled as such in the UI so I do not over-read it.

This answers a question worth real money: which version of me gets responses.

## Feature 4: Cover letter drafting

Deferred to v2 deliberately, since most applications do not need one and it is the feature most likely to produce something that sounds like AI wrote it.

If built, the constraints are non-negotiable and go in the prompt as hard rules:
- No filler openers. Never "I'm excited to apply."
- One honest paragraph on why applying, then specific relevant experience, then a clean close.
- No em dashes.
- Banned phrases list: "caught my eye", "lines up closely", "a couple of things that map to", "exactly where I do my best work", "your stack is basically mine".
- Runs through the same claim guard as the CV.

Same validator, different template.

## Feature 5: JD ingest quality of life

- Paste a URL, fetch and extract the JD text server-side.
- Duplicate detection: warn when a JD is 90% similar to one already applied to, which catches the same role posted through three agencies.

---

# Cross-cutting decisions

**Storage.** SQLite in v1. Move to Postgres only if this ever becomes multi-user, which is not planned.

**Secrets.** `ANTHROPIC_API_KEY` in `.env`, `.env` in `.gitignore`, `.env.example` committed. The key never reaches Angular. Every model call is server-side, same rule as Outreach Deck.

**Model choice.** Haiku for JD parsing, which is mechanical extraction. Sonnet for selection and summary, where judgment about relevance matters. Cost is trivial at this volume either way.

**Testing.** Pytest on the parser, the claim guard, the one-page loop, and the filename generator. These are the pieces where a silent failure puts a wrong claim on a real CV. Skip UI tests in v1.

**Repo.** Single repo, `frontend/` and `backend/`, one README with a screenshot walkthrough. Public, same as Outreach Deck. `master.md` contains a phone number, so either gitignore it and commit `master.example.md`, or strip the phone number and commit it as a portfolio artifact.

**CV entry for this project.** Only once real Angular code exists:

```
hired · Angular · FastAPI · Python · Claude API · Playwright
Built a CV tailoring tool that turns a pasted job description into a role-targeted one-page
PDF, generating from a master profile with per-project claim constraints, one-page enforcement
through a render-and-measure loop, and PDF export via headless Chromium browser automation.
```

Add `Currently learning: Angular` to the skills block now, and swap it for real placement once the frontend is genuinely built.

---

# The learning pass

Vibe-code the build. Then do this, because the point of the stack choice is defensibility in an interview, and generated code I have not read defends nothing.

**FastAPI, watch a short course first, roughly two hours.** Then read the codebase for: path operations and decorators, Pydantic request and response models, dependency injection with `Depends`, async versus sync route handlers and which one Playwright needs, error handling and `HTTPException`, and how `/docs` gets generated for free.

**Angular, I already know the syntax.** Read the codebase against the ten-item table above. The two that will not be obvious from reading alone are signals versus RxJS interop, and change detection with `OnPush`. Those are worth a focused hour each.

**The interview answer this produces.** "I built a tool I use daily to tailor my CV per application. Angular front-end, FastAPI back-end. The interesting problem was constraining an LLM so it can never claim something I cannot defend, which I solved by having it return bullet ids from a fixed pool rather than generated text, plus a validation layer that checks numbers and qualifiers survive rephrasing. One-page output is enforced with a render-and-measure loop rather than by asking the model nicely."

That is a real engineering answer about a real constraint, and it is true.
