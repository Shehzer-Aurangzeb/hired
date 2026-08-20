# Progress

## Where we are

Session paused 2026-08-16. Done: Phase 1 (backend parser and `GET /api/profile`)
and the complete v1 frontend. Everything below is the detail.

**Blocked on you, and only you**

1. `backend/profile/master.md`. Phase 4 (claim guard) cannot be written against
   a fixture, and Phase 2 has nothing real to render. Start from
   `backend/tests/fixtures/master.md`, which is structurally complete.
2. Your current CV, in the repo. Phase 2 exit criteria is "visually identical",
   which is not checkable against a description.
3. Three real saved job descriptions, for testing the Phase 5 parser.

**Next unblocked work, in order.** None of these need the CV:

| # | Thing | Why now |
|---|---|---|
| 1 | `core/filenames.py` + pytest | Free-standing, pure function, twenty minutes |
| 2 | `db.py` + `models/application.py` + `/api/applications` routes | Free-standing. Unblocks the frontend applications screens off mocks |
| 3 | `config.py` + `.env` + `services/claude_client.py` | One place that talks to Anthropic |
| 4 | `services/jd_parser.py` + `POST /api/generate` | Needs the three saved JDs |
| 5 | `services/selector.py` | Needs `master.md` and the claim guard |

As each route lands, set `USE_MOCKS = false` in `frontend/src/app/core/api.ts`.

**Restart the two servers**

```
cd backend  && HIRED_MASTER=tests/fixtures/master.md .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npx ng serve
```

Drop the `HIRED_MASTER=` prefix once `backend/profile/master.md` exists.

---

## Phase 1 — FastAPI skeleton, profile parser, `GET /api/profile`

Done. 6 tests pass.

**Files**

```
backend/
  app/models.py            Identity, Title, Summary, SkillLine, ClaimBoundary,
                           Bullet, Project, Experience, Profile
  app/profile_parser.py    master.md -> Profile
  app/main.py              FastAPI app, CORS for localhost:4200, GET /api/profile
  conftest.py              empty, puts backend/ on sys.path for pytest
  requirements.txt
  tests/test_profile_parser.py
  tests/fixtures/master.md a structurally complete sample, not the real profile
.gitignore                 ignores backend/profile/master.md (phone number)
```

**Parser approach.** `master.md` is markdown headings wrapping YAML bodies, so
the parser splits on `# / ## / ###` and hands each body to `yaml.safe_load`.
No hand-rolled tokenizer. Project `id` is slugged from its heading
(`### Dedicate` -> `dedicate`) unless the body sets `id:` explicitly.

**Decisions taken**

- No `POST /api/profile/reload`. The file is re-parsed per request, so there is
  nothing cached to invalidate. Add caching plus reload only if parse time
  ever shows up in a profile.
- No `config.py`, `deps.py`, `db.py`, `services/`. Nothing needs them until
  Phase 2 and later.
- Parser rejects duplicate bullet ids. A duplicate would let the Phase 6
  selector point at the wrong claim.
- `start` / `end` coerce to string, since YAML turns `2024-11-01` into a date.

**Writing `master.md`: the one gotcha.** Section bodies are real YAML, so a
list item that begins with a quote must be quoted end to end:

```yaml
# wrong, YAML parse error
- "~50% reduction in repeat API calls" must always carry the word "estimated"

# right
- '"~50% reduction in repeat API calls" must always carry the word "estimated"'
```

Headings only at column 0. Indent any YAML comments so they are not read as
section headings.

**Run**

```
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
.venv/bin/uvicorn app.main:app --reload      # needs backend/profile/master.md
```

**Next:** Phase 2, Jinja template plus Playwright PDF export from hardcoded
JSON, matching the current CV exactly. No AI yet.

---

## Angular shell (part of Phase 7, pulled forward)

Phase 2 is blocked on having the current CV to match, so the Angular half
started early. Only the part that a real backend endpoint already supports.

**Angular 20, not 21+.** Node here is v22.21.1 and Angular 21 needs v22.22.3 or
newer. Angular 20 is standalone plus signals, which is everything the plan asks
for. Upgrade Node and `ng update` later if it is ever worth it.

**Files**

```
frontend/src/
  index.html                            title is lowercase "hired"
  styles.css                            colour tokens plus base styles
  app/app.ts .html .css                 shell, topbar, router-outlet
  app/app.config.ts                     provideRouter, provideHttpClient
  app/app.routes.ts                     /profile, everything else redirects there
  app/core/models.ts                    TS interfaces mirroring app/models.py
  app/core/profile.service.ts           httpResource over GET /api/profile
  app/features/profile/profile-page.*   read-only view of the parsed profile
```

**The profile page earns its place.** It renders every bullet with its id and
priority, marks blocked bullets, outlines gated skill chips in amber, shows
each project's claim boundary in a `<details>`, flags projects that have no
claim boundary at all, and counts summary characters against `max_chars`. That
is the fastest way to see whether a hand edit to `master.md` parsed the way you
meant it to.

**Decisions taken**

- No `/generate` or `/applications` route. They need Phase 6 and Phase 9
  endpoints. Building UI against an API that does not exist yet means building
  it twice.
- No `error.interceptor.ts`. There is one service, and `httpResource` already
  exposes `error()`. Add an interceptor when there are three services.
- No `proxy.conf.json` and no `environment.ts`. The backend already sets CORS
  for `localhost:4200`, so the service holds one `API` const.
- `httpResource` over `toSignal` + `catchError`: one line instead of ten, and
  it gives `value` / `error` / `isLoading` for free. It is experimental in v20.
  `toSignal` interop still gets learned in Phase 7, since `POST /api/generate`
  will be a plain `HttpClient` call.
- No UI tests, per the plan. `ng build` does full AOT template type checking
  against `core/models.ts`, which catches the errors that matter here.

**`HIRED_MASTER` env var** added to `backend/app/main.py`, so the backend can
run against `tests/fixtures/master.md` while the real `master.md` is still
being written.

**Run both**

```
cd backend && HIRED_MASTER=tests/fixtures/master.md .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npx ng serve
```

Then open http://localhost:4200. Drop the `HIRED_MASTER=` prefix once
`backend/profile/master.md` exists.

**Next:** still Phase 2, and it needs the current CV in the repo.

---

## v1 frontend complete

Every v1 screen is built, styled and verified in a real browser. The generate,
export and applications endpoints do not exist yet, so a mock interceptor answers
them from fixtures. `GET /api/profile` is real and is never mocked.

**Tailwind v4** via `@tailwindcss/postcss` and `.postcssrc.json`. No `tailwind.config`
file: v4 takes tokens from an `@theme` block in `src/styles.css`.

**Design direction: dense pro tool.** Inter, 13-14px body, slate surfaces, one
green accent for the primary action, amber for soft flags, red for hard blocks.
Light and dark defined together in `styles.css` so neither drifts, with an
inline script in `index.html` that sets the class before first paint so a
dark-mode reload does not flash white.

**Files**

```
frontend/src/
  index.html                              Inter, theme pre-paint script
  styles.css                              @theme tokens, .btn/.card/.field/.chip/.badge
  app/app.{ts,html}                       top bar, nav, theme toggle, toast host
  app/app.config.ts                       router + http with mock and error interceptors
  app/app.routes.ts                       /generate /applications /applications/:id /profile
  app/core/
    api.ts                                API const and the USE_MOCKS flag
    models.ts                             profile types plus the generate/application contract
    profile.service.ts                    httpResource over the real endpoint
    generate.service.ts                   holds the draft across route changes
    applications.service.ts               list, get, updateStatus, pdfUrl
    mock-data.ts                          fixtures: one generation, six applications
    mock.interceptor.ts                   answers the unbuilt routes, delete when they land
    error.interceptor.ts                  one toast per failed call, then rethrow
    toast.service.ts                      signal list, auto dismiss
    theme.ts                              signal + effect, persisted to localStorage
  app/shared/
    icon.ts                               15 inline Lucide paths via @switch
    toast-host.ts                         aria-live region, bottom right
  app/features/
    generate/generate-page.{ts,html}      three panes: JD form, fit + flags + bullets, preview
    generate/bullet-selector.{ts,html}    CDK drag-drop, checkboxes, keyboard reorder
    applications/applications-page.*      table, search, status filter, follow-up flag
    applications/application-detail.*     what was sent, why, the posting, status control
    profile/profile-page.*                parsed master.md, filterable
```

**Decisions taken**

- No `shared/ui` button/card/badge components. With Tailwind, an Angular wrapper
  around a styled `<button>` earns nothing, so those are CSS classes in
  `styles.css`. Only things that own behaviour are components: the bullet
  selector, the toast host, the icon.
- No icon dependency. 15 inline Lucide paths in one `@switch` template beat a
  package, and inlining avoids the `DomSanitizer` dance a path map would need.
- `fit-score-card` and `flags-panel` stayed inline in the generate template.
  They are presentational and had no state to own. Split them out when one of
  them grows behaviour.
- Mock interceptor rather than waiting for the backend. The fixtures in
  `mock-data.ts` are the worked example the backend has to reproduce, so they
  are the contract, not throwaway.
- `models.ts` adds `project_name` to `CvSection`, which the plan's sketch did not
  have. The UI needs a human label for the group header. The backend must send it.
- The preview pane is an HTML approximation, not the printed artefact. It gets
  swapped for an iframe of the Jinja render once Phase 2 lands.
- The one-page indicator is a character-count heuristic. The backend
  render-and-measure loop is the real judge; this only exists to warn before an
  export round trip.
- Drag-drop has a keyboard equivalent. Up and down buttons on every bullet,
  because drag alone locks out keyboard users.
- The wordmark hides below the `sm` breakpoint. Labelled nav items matter more
  than branding, and at 375px both do not fit.

**Verified in headless Chromium** at 1440, 390 and 375 wide, light and dark:
every screen renders, the full generate flow works end to end against the mocks,
no console errors, no horizontal overflow.

**When each backend route lands,** set `USE_MOCKS = false` in
`frontend/src/app/core/api.ts`. Delete `mock.interceptor.ts` and `mock-data.ts`
once all of them exist.

---

## Repo and UI pass

**It is a monorepo already**, and now it is a git repo. `frontend/` + `backend/`
+ `docs/` under one root is the layout `BUILD_PLAN.md` specifies. No nx, no
turborepo, no pnpm workspaces: two apps in two languages with separate package
managers share nothing at build time, so a build graph would be pure overhead.
Added `README.md`, renamed `hired_BUILD_PLAN.md` to `BUILD_PLAN.md` as the plan
asks, `git init` and a first commit. 55 files tracked, no `node_modules` or
`.venv` leaked.

**Requirement coverage panel** on the generate page, between the fit card and
the flags. It uses `parsed_jd`, which the API already returned and the UI was
throwing away. Every required and preferred skill gets a chip at one of three
levels:

| Colour | Meaning |
|---|---|
| Green | Named inside a bullet that is currently selected. Defensible. |
| Amber | On the skills line or a stack, with no bullet behind it. The question you do not want cold. |
| Red | A requirement the page never mentions at all. |

Evidence is bullet text only, deliberately. A stack line is a list, same as the
skills line, and listing a technology is not the same as having a sentence that
describes using it. That distinction is also what makes the panel react: deselect
the Next.js bullet and Next.js drops from green to amber while you watch.

Matching is a case-insensitive substring test, so "React" hits "React Native"
and a posting saying "ReactJS" misses "React" on the page. The synonym map
planned for `profile/skills_taxonomy.md` in v2 is the upgrade path.

**Other changes in this pass**

- `Cmd`/`Ctrl` `Enter` in the JD textarea generates, with the hint in the help line.
- The preview pane is paper white in both themes now. It represents a printed
  page; rendering it dark was wrong.
- Both sticky panes cap at `calc(100dvh - 4.5rem)` and scroll internally. A
  sticky element taller than the viewport hides its own bottom, which was
  putting the Generate button out of reach on short screens.
- Relative dates in the applications list and detail, exact date in the
  `title`. `Intl.RelativeTimeFormat` in `core/dates.ts`, no dependency.

Re-verified in headless Chromium at 1440 and 375, light and dark: no console
errors, no horizontal overflow, coverage counter moves on deselect.

---

## Beige theme, one mode, favicon

**Dark mode is gone, not hidden.** Deleted `core/theme.ts`, the header toggle,
the pre-paint script in `index.html`, the `.dark` token block, and the now
unused `sun` and `moon` icons. `color-scheme: light` so native controls follow.

**Palette: beige paper, near-black ink.** The app previews a document meant for
print, so a warm light ground is the honest backdrop.

| Token | Value | Role |
|---|---|---|
| `bg` | `#f0eadc` | page |
| `raised` | `#faf7f0` | cards, header |
| `surface` | `#e6dfcd` | table heads, subtle fills |
| `line` | `#dad1bd` | dividers |
| `line-strong` | `#9c8c68` | control edges, 3:1 as WCAG 1.4.11 wants |
| `fg` | `#14110c` | body text, 15.7:1 |
| `fg-muted` | `#57503f` | 6.7:1 |
| `fg-subtle` | `#665d4b` | 11px text, 4.95:1 |
| `ink` | `#1a1712` | primary button, focus ring |
| `accent` | `#2f6b4f` | covered, good |
| `warn` | `#7e5210` | soft flags |
| `danger` | `#9b2c21` | hard blocks |

The primary button is ink, not the green. One primary action per screen, and on
beige the highest-contrast thing on the page should be the thing you press.

**The CV preview stays white with neutral grey text**, deliberately. It is a
sheet of paper, not app chrome, and now that the page is beige it actually
reads as one.

**Contrast is verified, not assumed.** A script walks every rendered text node
on all four routes, resolves its real background through the ancestor chain,
and checks the ratio against the AA threshold for that font size and weight.
All four pages report zero failures. Re-run it from
`docs/contrast-audit.js` after any palette change.

**Favicon**: `frontend/public/favicon.svg`, a lowercase `h` in beige on an ink
rounded square, matching the plan's rule that the name is always lowercase.
Two stroked paths, legible at 16px. Deleted the default Angular `favicon.ico`;
an SVG icon covers every browser that matters and there is no build step.

**Also tidied:** added a meta description, deleted the default Angular
`frontend/README.md` since the root `README.md` covers running both apps.

---

## Generate page redesign

The old three-column layout worked but was 60% empty before generating, kept the
posting form in prime space after, and rendered the CV at 40% in the narrowest
column. Rebuilt around the fact that the page has two distinct jobs.

**Phase 1, no result yet.** Centered single column, ~44rem. The posting form is
the page. Under it, the thesis in three lines: ids not prose, boundaries per
project, one page measured. That is the only interesting engineering in the
project and it was previously invisible.

**Phase 2, result exists.** The form collapses to a header strip that names the
company, role, location, work mode and chosen headline, with `Edit posting` to
reopen it. Below that a **sticky decision bar** at `top-12` carrying fit score,
required-backed count, page fill, bullet count and Export. Those are the four
numbers that decide whether to send it, so they never scroll away.

Then two columns, `minmax(0,1fr)` and `34rem`: decisions on the left (reasoning,
coverage, flags, bullets), the sheet on the right.

**The sheet renders at true Letter width.** 816px, the real 8.5in at 96dpi,
scaled with CSS `zoom` and a Fit 62% / Actual size toggle. `zoom` rather than
`transform: scale`, because the parent box shrinks with it and no height
compensation is needed.

**Also in this pass**

- The title variant select shows the actual headline text underneath and says
  what it does. It swaps the CV headline and the summary paragraph.
- `Reset to suggested`, visible only once the selection has drifted from what
  the selector returned. Compares exclusions and bullet order.
- The generating state names the three pieces of work instead of showing a bare
  spinner. It is a static list, not a stepped bar: `/api/generate` is one round
  trip, so claiming "step 2 of 3" would be invented.

**Two layout bugs found and fixed during verification**, both the same root
cause. A CSS grid item defaults to `min-width: auto`, so it refuses to shrink
below its content: the 816px sheet widened the page instead of scrolling in its
own container, and the long headline chip pushed 3px past the viewport.
`min-w-0` on the aside, `truncate` on the chip.

**Deliberately not built:** inline bullet text editing, which would be a hole
straight through the claim guard, since bullet text is supposed to come from
`master.md` only. Also no dragging bullets between projects, no j/k navigation,
no onboarding tour.

Verified at 375, 414, 768, 1024, 1280 and 1440: no overflow at any width, all
text passes WCAG AA, sticky bar pins correctly, reset and zoom and the edit
round trip all behave.

---

## Mock scenarios

The mock ignores the pasted text and always returned the same 8/10 result, so
five UI branches had never rendered once: hard-block flags, the disabled Export
button, page fill over 100%, the generate error path, and the empty
applications state.

Append `?mock=<name>` to any URL:

| Scenario | What it shows |
|---|---|
| *(none)* | Air Canada, 8/10, three warnings. The happy path. |
| `weak` | Fit 3/10 with five gaps. Exercises the red score tone. |
| `blocked` | Two hard blocks. Export goes disabled and the bar says why. |
| `overflow` | Four copies of every section, 24 bullets, 121% of a page, red fill bar. |
| `error` | `POST /api/generate` returns 500. Toast, and the form keeps your text. |
| `empty` | Applications list comes back empty. |

The variants are derived from `MOCK_GENERATE` rather than hand-written, so they
cannot drift from the real response shape. The interceptor logs the list to the
console on load. All of it is deleted along with the mocks.

**This immediately found a real bug.** `error` raised no toast, because
interceptors were registered as `[mockInterceptor, errorInterceptor]`, which
makes the mock outermost. When the mock short-circuits with an error it never
calls `next()`, so the error interceptor was never reached. Once the real
backend lands the mock would pass through and the toast would have started
working again, which is exactly the kind of bug that hides until the day you
switch `USE_MOCKS` off. Swapped to `[errorInterceptor, mockInterceptor]` so the
error interceptor is outermost and sees failures from either source.

All six scenarios verified: contrast passes AA and nothing overflows at 375.

**Not built, and deliberately:** v2 screens. The skills-frequency dashboard and
the reply-rate charts aggregate over twenty-plus saved applications. With an
empty database they are charts of nothing, and the plan gates them behind real
volume.
