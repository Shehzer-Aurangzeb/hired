# Progress

## Where we are

Updated 2026-08-23. **Nothing is mocked any more.** Every route is live: auth,
the profile and its parser, the fit check, the selector and its claim guard, the
PDF export, applications. Everything below is the detail, oldest first.

**Blocked on you, and only you**

1. Your real profile, written against `docs/master_template.md`. Everything runs
   against the starter template today, which has placeholder bullets, so the
   selector is choosing between sentences that say nothing.
   `docs/master_interview_prompt.md` is the interview that produces the real one.
2. A deploy target. It decides SQLite plus a volume versus Postgres, and whether
   the image ships its own Chromium.

**Next work, in order**

| # | Thing | Why now |
|---|---|---|
| 1 | Run the interview, save a real `master.md` | Everything below is guesswork without it |
| 2 | Tune the selector prompt against real bullets | The only way to know if it picks well |
| 3 | Match `templates/cv.html` to the reference CV | Layout, once there is real content in it |
| 4 | The one-page budget loop | Needs a page that actually overflows |
| 5 | Frontend tests | There are none, and the flow is now worth pinning |

**Restart the two servers**

```
cp backend/.env.example backend/.env      # then fill HIRED_SECRET_KEY
cd backend  && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npx ng serve
```

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
(`### Ledgerline` -> `ledgerline`) unless the body sets `id:` explicitly.

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
being written. *(Superseded: the profile moved into the database. See the
storage section below.)*

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

## First-run setup

Signing in with no profile lands on `/setup`. `profileGuard` sends every other
route there, `setupGuard` sends you away once a profile exists, and the nav
stays hidden until then, since none of it works yet.

**Three ways in**: paste, upload a `.md`, or start from a template. The template
is a commented skeleton that explains each section, with the claim boundary
written before the bullets so the shape teaches the rule.

**Validate before save, never after.** The result clears the moment the text
changes, because a stale green tick is worse than none. Errors carry a line
number and quote the offending line, so you are not counting rows. The summary
lands as four tiles: projects, bullets, blocked, missing boundaries.

The mock validator is a line scanner rather than a YAML parse, but it catches
the mistakes that actually happen, including the quoting trap that broke this
project once already:

```yaml
- "~50% reduction in repeat API calls" must always carry "estimated"   # breaks
- '"~50% reduction in repeat API calls" must always carry "estimated"' # fine
```

Uploads are capped at 512 KB client-side and the profile persists in
`sessionStorage` under mocks, same as the session.

**A real bug came out of the auth work.** `authInterceptor` adds
`withCredentials` to every request, including the live `GET /api/profile`, and
the backend's CORS had no `allow_credentials`, so the browser blocked it. Fixed
in `backend/app/main.py`. It is required anyway once the cookie is real, and it
is why `allow_origins` cannot become a wildcard. Backend tests still pass.

**Mocked routes**: `GET /api/profile/source`, `GET /api/profile/template`,
`POST /api/profile/validate`, `PUT /api/profile/source`. The save carries
`expected_updated_at` so the backend can reject a stale write with 409.

Verified: first run redirects to setup, template loads and validates clean,
breaking the quoting rule fails with the right line, fixing it passes, saving
lands on `/generate` with the nav back, and `/setup` then redirects to
`/profile`. Contrast passes, no overflow at 375, 768 or 1440.

---

## Lock screen and auth

Three amendments to `BUILD_PLAN.md`, all deliberate: the app will be deployed
rather than only run locally, it gets a password gate, and the profile moves
into the database. The plan ruled out all three for v1.

**Why the profile moves.** A container filesystem is ephemeral, so a
`master.md` on disk vanishes on redeploy unless a volume is mounted. Durable
storage is already needed for `applications.db`, so putting the profile there
means one thing to persist instead of two. `parse()` only needs to take a
string instead of a `Path`; the file stays the import and export format.

**How auth works.** The password is hashed server-side. Login returns an
httpOnly session cookie, so the browser never holds anything a script can read,
and `withCredentials` carries it. On boot the app asks
`GET /api/auth/session` once, shared between the guard and the shell.

- `authGuard` on every route but `/login`, redirecting with `?next=` so a deep
  link survives signing in.
- `guestGuard` on `/login`, so an existing session does not sit on the gate.
- `authInterceptor` runs first and turns any 401 into a sign-out plus a bounce.
  Calls to `/api/auth/` are exempt, since a wrong password belongs in the form
  rather than in a redirect.
- The header, nav and sign-out only render once authenticated.

**The screen itself** is the project's front door, so it explains the project.
Two columns: what hired does and the three claims that make it interesting on
the left, the gate on the right. The posting-to-CV illustration is abstract
grey bars on purpose, since a realistic-looking CV there would be a fabricated
document.

States covered: idle, checking, wrong password, rate limited with a live
countdown and a disabled button, and server unreachable, which is worth its own
message because a free-tier host can take half a minute to wake.

Reveal toggle, `autocomplete="current-password"`, `aria-invalid`, the error in
an `aria-live` region with `role="alert"`, and focus returned to the field on
failure.

**Mocked routes**: `GET /api/auth/session`, `POST /api/auth/login`,
`POST /api/auth/logout`. Three misses trigger a 429 with `retry_after`, the
same shape the backend will use. The demo password is `hired` and the hint on
screen is behind `USE_MOCKS`.

The mock session persists in `sessionStorage`. Module state reset on every
reload, which signed you out on refresh; a real cookie would not. Lockout state
is deliberately not persisted.

Verified end to end: deep link redirects with `next`, login honours it, reload
keeps the session, `/login` bounces an authenticated visitor to `/generate`,
sign out clears the shell, three failures lock the form. Contrast passes on the
lock screen and all four app routes, nothing overflows from 375 to 1440.

---

## Application detail

Brought in line with the other two pages, and two pieces of duplicated logic
were pulled out rather than copied a third time.

**`core/pipeline.ts`** now owns the stage list, the validated segment colours,
`FOLLOW_UP_DAYS`, `inSegment`, `waitingDays`, `statusClass` and `scoreTone`. The
list page and the detail page both import it, so the ghosted rule and the
palette cannot drift apart.

**`core/coverage.ts`** owns `computeCoverage`. It takes plain strings rather
than a CV shape, so the generate page (a fresh `GeneratedCv`) and the detail
page (a saved `Application`) can both call it.

**Headline numbers**: Fit score, Requirements backed, Bullets sent, Days out.
The Days out tile turns amber when the record has gone quiet, reusing the same
`inSegment(a, 'ghosted')` rule as the list.

**Status is a track, not a chip row.** Generated → Applied → Replied →
Interview → Offer reads left to right with completed steps ticked and the
current one in ink. Rejected sits apart on the right as a terminal state, and
selecting it takes the record off the track entirely.

**"What they asked for"** shows the posting's requirements against the bullets
that actually printed, green when a bullet named it and red when nothing did.

Deliberately two states here, not the three on the generate page. The record
stores the bullets and the summary but not the skills line, so "on the page but
unbacked" cannot be distinguished from "absent". The caption says exactly what
was matched rather than implying a comparison the data cannot support. Storing
`skills_lines` on the record would buy the third state, and is not worth a
column that only this display would read.

**Notes** gained a save indicator in the card header: "Saves when you click
away", then "Saving…", then "Saved".

Verified: the status track moves through every stage and off it, notes save,
the generate page coverage counter still reacts to deselection after the
extraction, the list still renders every status. Contrast passes, no overflow
at 375, 768, 1024 or 1440.

---

## Applications: polish pass

**Two clear crosses in the search field.** WebKit draws its own on
`input[type=search]` and we draw a styled one. Killed the native
`::-webkit-search-cancel-button` in `styles.css` rather than on one input, since
the profile filter has the same field.

**Search** is its own `.search` class now: larger, rounded, a soft focus ring
via `color-mix`, a leading icon, and a `/` key hint that turns into the clear
button once there is text. Pressing `/` anywhere on the page focuses it.

**Headline numbers moved to their own row** as four larger `.stat-lg` tiles:
Total, Sent, Reply rate, Need follow-up. The follow-up tile is a button that
filters to Ghosted, which let the amber banner above the table go. Same
information, one less stacked alert.

**Pipeline band** got taller with fully rounded ends, and hovering a segment
fades the others to 35% so the one under the pointer reads clearly. The legend
became pill buttons carrying a dot, a label, a count and a percentage, matching
the chip language used elsewhere.

**Two bugs found while verifying.** `onKey` called `target.closest` on
`event.target`, which is `document` when nothing is focused, so pressing `/`
with no focus threw. And the PDF dialog framed a URL with no backend behind it,
so it 404'd; under `USE_MOCKS` it now explains that the export endpoint arrives
in Phase 2 instead of showing a browser error page.

Contrast passes, no overflow at 375, 768, 1024 or 1440.

---

## Applications: pipeline band, row click, PDF in place

**Rows are clickable.** `openRow` ignores clicks that land on an `a`, `button`,
`select`, `input` or `label`, so the status control still works. The company
anchor stays for keyboard and middle-click.

**A status select bug shipped in the previous commit.** Every row displayed
"Generated" regardless of its real status. `[value]` on a `<select>` is applied
before the `@for` options exist, so nothing matches and the control falls back
to the first option. Writing the status worked, which is why it passed the
earlier check; only the display was wrong. Fixed with `[selected]` per option.

**The PDF opens in place.** A native `<dialog>` with an `<iframe>`, loaded only
once opened. The browser already ships a PDF viewer, so embedding one would be
a dependency for something built in. Download stays as a secondary icon button.

**Pipeline band.** A stacked horizontal bar over the whole set, ordered live
stages first and dead ends last: Not sent, Waiting, Replied, Interview, Offer,
Ghosted, Rejected.

`Ghosted` is derived, not stored. It is status `applied` sitting longer than ten
days, which is the state you actually care about and the schema has no column
for.

Colours were run through the dataviz validator against the beige card surface
rather than picked by eye. The first four attempts failed: red beside brown
broke the CVD gate, grey beside amber broke the normal-vision floor at ΔE 11.1,
and the amber only reached 2.4:1 against beige. The passing set is

```
waiting #3a6ea8 · replied #a86a08 · interview #0a7f66
offer   #6b4fa8 · ghosted #8b8378 · rejected  #b23b2c
```

in that exact left-to-right order. Re-run
`node scripts/validate_palette.js` from the dataviz skill if the order changes.
`Not sent` is hatched rather than a seventh hue. `Ghosted` sits below the chroma
floor on purpose, since "nothing happened" should read as absence of colour.

Counts were briefly printed inside the segments and failed contrast on amber and
grey. They were duplicate information, since the legend already lists every
count, so they were removed rather than recoloured.

**The legend is the filter**, which let the separate status chip row be deleted.
Two controls doing the same job is one too many.

**Header** carries a subtitle and three stat tiles, Total, Sent and Reply rate,
reusing the `.stat` classes from the generate bar. Search is taller with a clear
button.

---

## Applications screens

**Inline status change.** Marking something applied is the most frequent action
in the app and it used to cost a page visit. Every row now carries a status
select that patches and updates the row in place. The filter counts recompute
live.

**Follow-up is the point of the list.** Anything in Applied for more than ten
days sorts to the top, gets a warm row tint and a "N days, no reply" line, and
a banner above the table says how many there are.

**The detail page shows the bullet text, not ids.** It used to list
`ledgerline-caching` and nothing else, which is useless three weeks later when
the whole promise of the view is interview prep.

That needed a contract change rather than a frontend join. Joining
`selected_bullet_ids` against the live profile would render today's `master.md`
wording, so editing a bullet later would make this page confidently show
something the employer never read. In a tool built around not overclaiming,
that is the wrong bug to ship. The record carries the text instead:

```python
selected_bullets: list[dict] = Field(sa_column=Column(JSON))
# [{"id": "ledgerline-caching", "text": "Built the data layer with...",
#   "project_name": "Ledgerline"}]
```

`selected_bullet_ids` stays, because the v2 "which bullets get replies" question
aggregates on ids. `SentBullet` in `core/models.ts` mirrors it.

**Notes are editable**, saved on blur. `notes` was already a v1 column and it is
what you want to write straight after a recruiter call.

**Cards below `md`, table above.** The table used to scroll sideways on a phone.

`ApplicationsService.updateStatus` became `patch(id, changes)`, since status and
notes were about to be two near-identical methods.

**Not built:** kanban, reply-rate charts, timeline metrics. All v2, all gated
behind twenty real applications. Column sorting is YAGNI at six rows.

Contrast passes on every route, no overflow at 375, 768, 1024 or 1440.

---

## Legibility pass on the generate result

Review said the numbers were unreadable, the section headings faded into the
page, the coverage chips were hard to tell apart, and the two header actions did
not look like buttons.

**The decision bar is four labelled stat tiles**, each a bordered box with a
20px value and a small caption, replacing a single quiet run of text. The
captions say what the numbers mean, and each tile carries a `title` with the
full explanation:

| Tile | Meaning |
|---|---|
| Fit score | The selector's judgement of the match. |
| Requirements covered | Required skills a selected bullet actually names. Skills line entries do not count. |
| Page filled | Estimated share of a one-page CV. A character heuristic; the backend render loop is the real measurement. |
| Bullets on page | How many are checked and will print. |

"39% of one page" and "6 bullets" were the two nobody could read. They now say
"Page filled" and "Bullets on page".

**Card headings borrow the bullet-section treatment**, a `bg-surface` strip with
a border under it, because that pattern already read clearly and the rest of the
page did not. `.section-title` also moved from `fg-muted` to `fg`.

**Coverage chips are filled, not outlined.** Green, amber and red now carry their
soft background as well as the border, split into Required and Preferred groups
with a legend underneath. Outline plus a small icon was not enough separation.

**"Blocked by the claim guard"** is a bordered red badge rather than loose text.

**The two header actions are `btn-outline` with icons.** They were `btn-ghost`,
which is invisible until hover.

**The sheet has a real page body**, `min-h-[1056px]`, 11in at 96dpi. A three
project CV used to render as a floating block that stopped halfway, which read
as broken. It now reads as a short CV on a full page, which is what it is.

New classes in `styles.css`: `.card-head`, `.stat`, `.stat-value`, `.stat-label`.

All six routes still pass the contrast audit, nothing overflows at 375, 768 or
1024.

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

**The scenarios run on load.** First version only applied the scenario to the
next Generate call, so typing the URL dropped you on an empty form and looked
like nothing had happened. `GenerateService` is root-scoped and holds the
result, which made it worse: navigating in-app kept the previous result on
screen. Now `GeneratePage` checks for the param in its constructor and fires a
generate with a canned posting, so the URL alone shows the state. Plain
`/generate` is untouched and still opens an empty form.

That block imports from `mock-data.ts` on purpose. When the fixtures are
deleted the import breaks loudly, which is the cue to delete the block too.

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

## Profile screen

Two tabs on one route, `?tab=` in the URL so reload and back behave.

- **Browse** — the parsed profile. Sticky project index at `lg+`, a filter that
  reports "3 of 12 projects", and the claim boundary promoted out of a
  `<details>` onto the card, because it is the reason the tool is trustworthy.
  Each card has an Edit button that switches tabs and drops the caret on that
  project's `###` heading in the source.
- **Edit source** — raw markdown with a scroll-synced line gutter that reddens
  the lines the validator complained about. Same validate-before-save flow as
  onboarding. Save is disabled until validation passes and the buffer is dirty.
- Health row above the tabs: projects, bullets, blocked, no boundary. Blocked
  and no-boundary are the only two that can be wrong, so they are the only two
  that get colour.

Protecting the only copy of the CV data:

1. `canDeactivate` + `beforeunload` on unsaved edits.
2. `expected_updated_at` on PUT; a 409 raises a conflict panel offering "load
   theirs" or "keep mine and overwrite" instead of silently clobbering. The mock
   implements the 409, and `?mock=conflict` forces it so the branch is reachable.
3. Export to `master.md` from the header, always available.

Two bugs found by testing rather than by reading:

- `/profile?tab=edit` entered directly never loaded the source, so the editor
  rendered empty and one Save would have wiped the profile. The source now loads
  in the constructor, which also makes the "Saved 2 hours ago" label true on
  both tabs.
- The mock login lockout counted failures but only reset them on a *successful*
  login, which the lockout itself blocks. Three wrong guesses and the correct
  password was refused forever. Now a `lockedUntil` timestamp that expires.

Skipped: structured/form editor (the markdown is the format), version history
(needs backend storage; export covers it), syntax highlighting (a CodeMirror
dependency for one textarea).


## Storage: SQLite, two tables

SQLite over NoSQL, because the "we will add features" argument is already
answered by JSON columns — `jd_parsed`, `gaps`, `selected_bullet_ids` and
`selected_bullets` are all JSON — while `ORDER BY created_at` and
`WHERE status = ?` still work. NoSQL would be a service to run for a few
hundred rows and one user. SQLModel is SQLAlchemy, so a Postgres URL is the
only change needed if the deploy target has no persistent disk.

`app/tables.py`

- **`profile_source`** — the master markdown, one row, `CHECK (id = 1)`. On disk
  it would not survive a redeploy, and it is the only copy of the CV data.
- **`application`** — the plan's table plus `selected_bullets` (the printed text,
  not a join against today's profile) and `pdf` as **bytes rather than a path**.
  A hundred applications is about 8 MB, which removes the second reason to need
  a writable disk and makes a backup one file. `CHECK` on `status`.

`app/db.py` — engine, `SessionDep`, `create_all` on startup. No Alembic: two
tables and one user means a schema change is a hand-written `ALTER TABLE`.
WAL and `foreign_keys` pragmas on SQLite, because "database is locked" is
reachable with one user and two tabs.

`app/settings.py` — pydantic-settings, `HIRED_` prefix, `.env` locally.
`secret_key` has **no default**: a shipped default signs forged sessions.
The password is `HIRED_PASSWORD_HASH` (scrypt, stdlib) rather than a table —
there is no change-password screen to justify one, and a table needs a seeding
path. Sessions are a signed cookie via Starlette's `SessionMiddleware`, so
there is no session table either.

`GET /api/profile` now parses the database row and 404s when none exists.

**One frontend fix this forced:** `ProfileService.profile` was an unconditional
`httpResource`, so the shell fetched the parsed profile on the *lock screen* —
a 404 toast today and a 401 redirect once auth lands. The URL is now conditional
on `authenticated() && exists()`, which leaves the resource idle until there is
something to fetch and someone allowed to fetch it.

**Next:** auth routes, then the profile source routes, which together take
`USE_MOCKS` from "everything" down to generate and export.

## Parser: hardened, and widened to a whole CV

Deliberately still deterministic. Claude is used at *write* time, not read time:
if the model parsed `master.md`, the claim guard would be checking Claude
against Claude, and that is the one place in this app where determinism is
load-bearing.

**Hardening.** Every failure now raises `ProfileError` with the line in the file
you typed, which is what makes a real `/api/profile/validate` possible:

- A column-0 `# comment` is a YAML comment again, not a section. It used to end
  the section it sat in and silently orphan everything below.
- A near-miss section name is an error with a suggestion, not silence.
  `# Experiance` used to make the entire work history disappear.
- YAML errors carry a translated absolute line: `line 62: ### Ledgerline is not
  valid YAML: expected <block end>...` rather than an offset into a fragment.
- A list section given a mapping says so instead of coming back empty.
- Duplicate `# Section`, duplicate project id, BOM, and CRLF all handled.
- Only `name` is required on Identity. A missing phone number is incomplete, not
  unparseable.

**This caught a live bug.** The shipped starter template contains four column-0
`#` comment lines. Under the old rule they were section boundaries, so the
template every new user starts from parsed to **empty titles and zero bullets**
— the claim boundary and the entire bullets block fell into a nonexistent
section. It looked fine only because the mock validator counted lines with a
regex instead of parsing. It now round-trips: 2 titles, 1 project, 2 bullets.

**Widened.** `Link {label, url}` accepts three shapes, because people write
links three ways and all three are unambiguous:

```yaml
links:
  - label: Repo
    url: github.com/me/thing
  - Repo: github.com/me/thing
  - github.com/me/thing        # label taken from the host
```

On `identity` for anything not already a named field (Dribbble, Stack Overflow,
a paper), and on `project` for repo / live / case study. Plus three new optional
sections: `# Education`, `# Certifications`, `# Languages`. All optional, so
existing profiles keep parsing.

**Draft it with Claude.** A fourth way in on first-run setup, and a button on
the profile editor. Builds a briefing — never invent a metric, `cannot_claim` is
the important half, the YAML quoting rule — appends the template, copies it to
the clipboard and opens `claude.ai/new?q=`. About 4 KB of prompt in a 6 KB URL.
The clipboard copy is the one that always works; the query parameter is not ours
to rely on. Nothing generated reaches the profile without passing validation and
a human pressing Save.

**Next:** the repair endpoint (broken source in, fixed source out) needs an
Anthropic API key, which the generate and selector phases need anyway.

## Template and Claude prompt moved to the backend

Both are content, not code, and both get reworded far more often than the code
around them. `app/profile_template.py` holds the defaults so a fresh checkout
needs no config; `HIRED_PROFILE_TEMPLATE` and `HIRED_CLAUDE_BRIEFING` override
them, so a reword is an environment change and a restart.

The briefing may contain `{template}` to place the starter file; without the
placeholder the template is appended instead, so a rewritten briefing cannot
silently drop the file it is about. There is a test for exactly that.

`GET /api/profile/template` is now real, returning `{ text, claude_prompt }` in
one call. The frontend copy of the template is deleted along with its mock
route.

**Draft with Claude folded into "Start from a template".** It was never a fourth
way in — it produces the same file the template describes, so it belongs where
the template is. The template view now carries two buttons:

- **Copy prompt** — the route that always works, with a `document.execCommand`
  fallback for any context where the clipboard API is missing, and a tick on the
  button instead of a toast over the page.
- **Open in Claude** — `claude.ai/new?q=`, about 6 KB of URL. Convenient when it
  works, and not something the flow depends on.

Same pair sits in the profile editor footer for a rewrite rather than a first
draft.

## Setup screen: one scroll region, and a Claude-coloured button

The review step used to be a long scrolling page: intro copy, a toolbar, a
Claude panel, four big stat tiles, the problem list, a 22-row textarea and a
footer, all stacked. From `md` up it is now a fixed-height flex column, so the
page itself never scrolls and the editor takes whatever height is left. What
went, and why:

- The intro copy stays on the chooser, where you read it. It is not needed again
  once you are editing.
- "Check it" appeared in both the toolbar and the footer. The footer is gone and
  both actions live in the top bar, which also puts Save where you can see it
  without scrolling.
- The four `stat-lg` tiles became chips in that bar, so the counts stay on
  screen while you edit instead of scrolling away above the file. Blocked and
  no-boundary only appear when non-zero.
- The problem list is capped at 26vh and scrolls; its count is a chip in the
  bar, because the count cannot live in the thing that scrolls away.
- The editor gained the line gutter from the profile page. Errors say "Line 62",
  so there needed to be a line 62 to look at.

Below `md` the page scrolls normally and the editor is a fixed 60vh. A phone
with a screenful of errors would otherwise have left a hundred-pixel editor.
Measured: 1440x900 gives a 631px editor and no page scroll, 434px with twelve
errors on screen, still no page scroll.

**Open in Claude** is `--color-claude: #b85a38` with white text and the burst
mark. That is Claude's coral deepened until white clears AA on it: the brand
value `#d97757` only reaches 3.1:1 against white, and every other button here
passes. Copy prompt stays a plain outline button beside it.

## Auth

`app/auth.py`. scrypt from the standard library, no `passlib`. The hash lives in
`HIRED_PASSWORD_HASH`, generated by `python -m app.hash_password`, which reads
the password with `getpass`, insists on twelve characters, and prints only the
hash. Sessions are a signed httpOnly cookie via Starlette's `SessionMiddleware`,
so there is no session table and nothing readable by script.

Three decisions worth writing down:

- **One dependency on the router, not one per route.** Every protected endpoint
  hangs off `APIRouter(prefix="/api", dependencies=[Depends(require_session)])`,
  so a route added later cannot forget to be protected — there is nowhere
  unprotected to put it.
- **The lockout escalates and expires on its own.** Five failures cost 30s, then
  60s, then 120s, capped at 15 minutes, and a correct password clears the
  escalation. A fixed lockout allows ten guesses a minute forever; a counter
  that only resets on success locks out the correct password, which is exactly
  the bug the mock had.
- **Global, not per-IP.** There is one password, so per-IP limiting just means
  rotating addresses. The cost is that a stranger who finds the URL can lock the
  owner out for a while, which is the cheaper of the two harms.

Also: no configured hash refuses every login with 503 rather than letting anyone
in, a malformed hash verifies as false, comparison is `hmac.compare_digest`, and
login clears the session before setting it so an earlier cookie cannot be
promoted.

The frontend's auth mocks are deleted along with `MOCK_PASSWORD` and the demo
hint on the lock screen. Verified in a browser against the real backend: the
cookie is `httpOnly=true sameSite=Lax`, invisible to `document.cookie`, survives
a reload, and is shared by a second tab — which the `sessionStorage` stand-in
never was. Five wrong passwords produce the real 429 and the countdown on the
button reads from `retry_after`.

**Two things this turned up.** The suite was reaching the developer's real
`hired.db`, so `conftest.py` now sets `HIRED_DATABASE_URL=sqlite://` before any
test module imports the app, and `test_auth.py` overrides `get_session` on top
of that. And `env_file=".env"` was relative, which resolves against the working
directory — the app only started when launched from `backend/`, and would have
failed at import on any deploy that starts elsewhere. It is anchored to the
package now.

**Next:** the profile source routes. Until they land, `GET /api/profile` reads a
real row while `/api/profile/source` is still mocked, so the two disagree about
whether a profile exists.

## Profile source routes

```
GET  /api/profile/source     -> { text, exists, updated_at }
POST /api/profile/validate   -> { ok, errors[], warnings[], summary }
PUT  /api/profile/source     -> 422 when it will not parse, 409 when stale
```

`validate_text` lives beside the parser it wraps. Errors come straight from
`ProfileError`, so the editor now shows what the app will actually do rather
than what a line-scanning stand-in guessed. Warnings are the things worth
knowing that are not reasons to refuse a save: projects without a
`claim_boundary` (named, up to three), no projects at all, and a summary over
its `max_chars`.

One error at a time. The parser is fail-fast because YAML is, and collecting
more would mean re-parsing after each guessed fix.

**PUT refuses three ways.** It will not write a file that does not parse; it
will not write over a copy that moved on; and it treats *no token at all* as the
same mistake, so first-run setup cannot wipe an existing profile if a guard ever
lets it through. A 409 hands back the current text so the editor can offer "load
theirs" or "keep mine".

**Timestamps.** SQLite's DATETIME silently drops `tzinfo`, so a stored UTC value
came back naive and the browser read it as local time — every "saved 2 hours
ago" was wrong by the reader's offset. The convention is now stated: naive UTC
in the database, offset marked back on by `stamp()` on the way out. The same
function produces the concurrency token, so what the client echoes back compares
equal.

The mock is down to generate, export and applications. `checkProfile`, the
sessionStorage profile and the source routes are all deleted.

**Two frontend bugs this exposed.**

- Angular evaluates a route's canActivate guards *concurrently*, so `profileGuard`
  was calling `/api/profile/source` before `authGuard` resolved — a guaranteed
  401 on the lock screen, complete with a "Not signed in." toast. Both profile
  guards now wait on the session and let authGuard's redirect win. The first fix
  called `inject()` inside the `switchMap` callback, which is outside the
  injection context; that broke every guarded navigation until it was flattened.
- `errorInterceptor` toasted 401s on top of the two places that already handle
  them: the login form shows a wrong password inline, and `authInterceptor`
  answers an expired session with a redirect. It skips 401 now.

Verified against the real backend in a browser: first run lands on `/setup`, the
template validates through the real parser, breaking the quoting rule reports
`Line 69` from `parse_text`, saving lands on `/generate`, and two tabs editing
the same profile produce a real 409 with "load theirs" pulling the winner's text.

**Next:** applications CRUD, the last unblocked chunk.

## Applications: saving is its own decision

The earlier plan had export create the record. That was backwards. The records
worth the most are often the ones you did *not* apply to — kept because the fit
check exposed a gap you cannot close yet — and those never had a PDF. So
`POST /api/applications` is the primary create path, and export attaches a PDF
to a row that already exists.

```
paste JD -> fit check
  ├─ out of your league        -> close it. Discard is "do not press save".
  ├─ worth keeping, not apply  -> POST /api/applications  status: skipped
  └─ worth applying            -> generate -> export -> mark applied
```

**Schema.** `pdf`, `filename`, `title_variant` and `summary_text` are nullable:
a kept posting never had a CV. What it always has is `jd_text`, `jd_parsed`,
`fit_score` and `gaps`, which is the part worth keeping.

**Statuses.** `generated` conflated two independent things — where you are with
an employer, and whether a PDF exists. The second is now just `pdf is not None`,
so the stage list is:

`saved` · `skipped` · `applied` · `replied` · `interview` · `rejected` · `offer`

`applied_at` is stamped the first time the status reaches one of the sent
states, and never rewritten by a later stage: it records when the employer got
it, not when you last touched the row.

**Routes** (`app/applications.py`, mounted under the session-protected router):

```
POST   /api/applications        201
GET    /api/applications        newest first, ordered by the database
GET    /api/applications/{id}
PATCH  /api/applications/{id}   status and notes, nothing else
GET    /api/applications/{id}/pdf
```

- `ApplicationOut` omits the `pdf` column entirely and exposes `has_pdf`, so a
  megabyte of base64 cannot leak into a list response by accident.
- PATCH takes an explicit two-field model rather than a partial row. Everything
  else is a record of what an employer actually received, and an API that can
  rewrite it turns the archive into fiction. It reads `model_fields_set`, so an
  explicit null clears the notes while a status change leaves them alone.
- The PDF filename is scrubbed before it reaches `Content-Disposition`: a
  newline in it would let the row write its own response headers. There is a
  test that tries exactly that.

`python -m app.seed_demo` inserts four postings covering the interesting states
so the screens have something real to render. It refuses to run over existing
rows, and gets deleted when export becomes a real caller.

**Next:** the frontend. New status vocabulary, a re-validated pipeline palette
(two new segments), "no CV for this one" states on the detail page, and deleting
`pdf_path`, which is in the contract and rendered nowhere.

## Applications: the frontend catches up

The mock is now down to **generate and export**. Auth, the profile and
applications all come from the real backend.

- `Application` mirrors the widened row: `title_variant`, `summary_text` and
  `filename` are nullable, `pdf_path` is deleted (it was in the contract and
  rendered nowhere), and `has_pdf` replaces it.
- Two new pipeline segments. The six colours and their order are untouched, so
  the CVD validation still holds — re-run to confirm, and the only failure is
  still the deliberate one (`ghosted` below the chroma floor). The never-sent
  stages share one neutral and are told apart by **hatch angle**, 45° for "Not
  sent" and 135° for "Passed on", which is the texture channel rather than two
  more hues the adjacency checks would have to survive.
- `isSent()` in `core/pipeline.ts` mirrors `SENT` in `tables.py`. The "sent"
  count used to be `status !== 'generated'`, which stops meaning anything once
  a row can be saved without a CV.
- The detail page handles a record with no CV: no View PDF button, a "No CV
  generated" chip, and the card that describes the CV describes its absence
  instead. **"Passed on" was unreachable** — the only terminal action was
  Rejected, which is the employer's answer, not yours. It is now beside it, and
  disabled once `applied_at` is set: passing on something already sent would be
  a record of something that did not happen.

**The bug worth writing down.** The backend typed `jd_parsed` as a bare `dict`
while the frontend contract promised `ParsedJd`. The seed stored
`{company, role}`, one computed called `.map` on an undefined
`required_skills`, and Angular blanked *most of the page* — status track, score
reasoning and job description all rendered as empty strips, with only a console
error to show for it. Fixed at the contract: `ParsedJd` is a real model on the
backend now, every field defaulted, so a sparse dict widens into a shape the UI
can render instead of a shape it dies on. A partial payload can no longer be
stored or served.

`python -m app.seed_demo` now seeds the starter profile too, since the guards
send you to `/setup` without one.

## 2026-08-23 — the master profile schema, eight sections wider

The profile grew from eight sections to sixteen. `Meta`, `Skill Evidence`,
`Projects`, `Publications`, `Awards`, `Availability`, `Gaps` and `Rules` are
new, and five of those never print on a CV: they exist so a posting can be
scored honestly before an evening goes into tailoring for it, and so the tool
can say "you cannot do this" instead of stretching a bullet to cover it.

**The rule the whole change was built under: a profile that saved yesterday has
to save today.** Every new field is optional with a default, and every new check
ships as a warning. The profile row is the only copy of the CV data, so refusing
a save costs more than almost anything it could protect against. The warnings
get promoted to errors the day there is a generator with something to protect.
`Certification.status` defaults to `earned` for the same reason: a file written
before that field existed has no status, and its certifications were real.

**The supplied template did not parse, at all.** It separates its sections with
column-zero `---`, which is a horizontal rule to a reader and a document
separator to YAML, and `safe_load` refuses a stream holding two documents. Every
one of the sixteen failed with `expected a single document in the stream`, which
says nothing about the rule that caused it. `_normalize` blanks them now, rather
than deleting them, so the line numbers in error messages still point at the
line the person typed. There is a test for that specifically.

**Projects have one namespace across two lists.** `# Projects` holds `###`
headings with no `##` parent, and they land in `Profile.projects` rather than
under a synthesized employer, because a company that does not exist has no
business appearing on a CV. But a bullet id resolves to exactly one project, so
`unique_ids` walks both lists together and the same project id in both is an
error. The Profile page groups the standalone ones under a header that prints no
role and no dates, which is a display grouping and says so.

**Thirteen new warnings**, capped at twenty with the tail collapsed into
`and N more`. A hundred warnings and none are the same thing to the person
looking at them. The ones worth naming: a bullet quoting a number with no
`metric` block, an `estimated` metric whose text does not say "estimated", a
project with bullets and an empty `cannot_claim`, and a `gated` skill with no
evidence, which is a gate that can never open.

**The existing fixture still saves, and warns seven times.** It was not changed.
A real profile written before any of these checks existed is exactly the case
worth keeping, so it is pinned as a characterization test instead.

**The Claude button was broken by the new template and had to be rebuilt.** The
combined prompt is 33KB, 48.6KB once URL-encoded, and `claude.ai/new?q=` cannot
carry that: something in the path refuses or silently truncates it. Truncation
is the dangerous half, because an interview running against half a template
looks like it is working. So the clipboard carries the prompt and the URL
carries a 197-character bootstrap that tells Claude to ask for the paste.
`openClaude` returns whether the copy landed, because the tab opens either way.
Two tests guard it: one on the URL length, and one asserting the frontend never
interpolates `prompt` into the URL at all, which is the check that actually
protects.

**The template and the briefing are copies.** `docs/master_template.md` and
`docs/master_interview_prompt.md` are where they are edited; the module holds a
copy, because reading them at runtime would mean shipping `docs/` inside the
container. A test compares the two, since a copy nothing checks is a copy that
drifts.

**A verification queue on the Profile page.** Blocked bullets and `unverified`
notes are one list, not two: same job, and splitting them means the shorter half
never gets looked at. It replaced the "Blocked" health stat, which had stopped
being the whole answer.

**Docs.** `docs/parser_contract.md` is the grammar and the complete error and
warning lists, corrected against the code wherever the two disagreed, with the
unbuilt parts kept under a heading that says so. The README's four stale claims
are fixed: there is no `HIRED_MASTER`, applications are real, and Claude neither
parses nor selects.

**Known and deliberately not fixed.** A fenced ` ```yaml ` body is a hard parse
error with a cryptic message, and the briefing tells Claude to return the file
in a markdown code block, so a person who copies the fence with the contents
hits it. A bare `cannot_claim:` with nothing under it is also a hard error
rather than a warning, which is the one save-blocking case that the governing
rule above would otherwise argue against. Both predate this change; neither is
in scope for it.

## 2026-08-23 — the flow, end to end

Paste a posting, get a score, decide, and only then spend a model call on a CV.
The whole thing runs against real services now. `USE_MOCKS`, `mock.interceptor.ts`,
`mock-data.ts` and `seed_demo.py` are all deleted.

**Gemini, not Claude, and not by preference.** The API key on hand is a Google
one. Nothing about the design cared: the fit check and the selector want a model
that returns JSON matching a schema, and `app/model.py` is one `httpx.post`
behind `HIRED_GEMINI_MODEL`. No SDK.

`gemini-2.5-flash` was the obvious pick and it **404s**: retired for new keys,
with a body naming `gemini-3.6-flash` as the replacement. That error is passed
through verbatim rather than shown as "502", because it contains the fix. One
fit check measures at ~2,500 tokens including thinking, so at five postings a
day the free tier's constraint is requests, not tokens, and eight a day is not
close to it.

**Two clamps, both from the model actually misbehaving.** It returned `55` on a
1-to-10 score and `5` on the 1-to-3 skill importance scale. The score is clamped
in the route; importance is clamped on `RequiredSkill` itself, so the selector
and any future seed get it too. Fixed once, where every producer routes through.

**The suite was making real API calls.** `conftest.py` cleared the password hash
so tests never depend on local secrets, but nothing cleared the Gemini key, so
the first run of `test_fit.py` sailed past the 503 branch and hit Google. The
tell was the runtime: 12.5s against 4s. Both spellings are cleared now.

**The selector returns ids and the guard is plain code.** Blocked bullets never
enter the pool. After the answer comes back, the guard refuses an id that does
not exist, refuses a blocked one that arrived anyway, enforces the `Rules` caps
the model was merely asked to respect, checks that each selected project's
`required_qualifiers` survived onto the page, and gates skills: a `gated` item
prints only when a project evidencing it was selected. All of it is a lookup, so
none of it is asked of a model.

**Export prints with Chromium via Playwright.** Jinja renders `templates/cv.html`,
Chromium prints it, so the preview and the PDF come from one layout engine rather
than two. The page count is measured height over page height rather than parsed
out of the file: it only has to answer "did it fit", which is the question the
budget loop will ask. The row's `title_variant`, `summary_text` and
`selected_bullets` are stamped at export from what was on screen, not from what
the selector said, because deselecting a bullet has to reach the archive.

**The Generate page is three screens now.** Paste, then a score with the gaps and
what the posting asks for, then the CV. Discard is not a button that deletes
anything: nothing is written until you press Keep or Generate, so closing the tab
costs nothing. Keeping without applying writes the posting and its gaps, which is
the record worth the most when you do not apply. Generate creates the row first,
so an abandoned generation still leaves the posting on file.

**Summary re-rolling is gone.** It was a model call that wrote prose onto a CV,
which is the one thing this app exists not to do. The button cycles the
title-and-summary pairs already written in `master.md`, swapping both together.

**Four parser bugs, all found by asking what a real paste looks like.** A code
fence around the file is now stripped, because the briefing asks Claude for a
markdown code block and the fence comes along with it. A written-but-empty list
(`cannot_claim:` with nothing under it) reads as empty rather than refusing the
save. Enum tokens case-fold, so a capitalised `Earned` certification no longer
silently never prints. And the education line lost a stray space before its comma.

**Verified end to end against real services**: paste to fit (9/10, gaps named),
generate, export, mark applied, landing on the detail page with a 47KB one-page
PDF served from the row. Zero console errors. 168 backend tests.
