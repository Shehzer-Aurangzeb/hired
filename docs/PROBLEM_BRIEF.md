# hired — system brief and open problems

A brief for an outside reader asked to improve this system. It describes what
the app does, the hardware and models it runs on, the exact flow, what has been
measured, what is still broken, and what has already been tried and rejected.
Everything numeric here was measured on 2026-10-15 unless stated.

---

## 1. What the app is for

A personal tool for one user. Paste a job posting, get back:

1. **A fit score** (1–10) with reasoning and a list of gaps — "should I apply?"
2. **A tailored one-page CV** as a PDF, saved next to the posting it was made for.

The user is a software engineer applying to junior/mid full-stack and front-end
roles in Canada. He has applied 67 times through this tool.

### The non-negotiable constraint: nothing invented

The CV must never contain a claim the user cannot defend in an interview. This
is enforced structurally, not by asking a model nicely:

- All experience lives in one hand-written Markdown file (`master.md`, ~50,000
  characters). It is a fixed pool of bullets, each attached to a project.
- The model is **never asked to write prose for the CV**. It returns **bullet
  ids**. The page is assembled from the user's own sentences afterwards.
- Each project carries `cannot_claim` (things it must not be used to evidence)
  and `required_qualifiers` (caveats that must appear on the page if the project
  appears). A guard checks these after assembly and raises warnings.
- The profile also records **gaps** — things the user explicitly cannot do.

An id the model returns that does not exist produces a warning, not invented
text. This property must be preserved by any proposed redesign.

---

## 2. Hardware and models

**Machine:** MacBook Pro 18,3 (M1 Pro), 16 GB unified memory, macOS.

**Local model:** `granite3.3:8b` (IBM, Apache 2.0) via ollama, Q4, 4.9 GB on
disk. Served with an explicit `num_ctx` of 12288.

Memory cost measured directly from `ollama ps`:

| num_ctx | resident |
|---|---|
| 4096 (ollama's default) | 5.7 GB |
| 12288 (what we use) | 7.1 GB |
| 16384 | 7.8 GB |

16384 left only 18% of system memory free, which is too tight because the user
works on the machine at the same time. 12288 is the largest window that fits the
biggest prompt with headroom.

**Throughput:** ~10 tokens/second generation. Prompt processing is much faster
(parallel); generation is sequential and memory-bandwidth bound. `"think": false`
is sent because reasoning tokens cost the same as useful ones and gave a 15×
speedup on extraction.

**Cloud model:** `gemini-3.6-flash` (free tier). **Currently unusable.** Over two
days it returned either:

```
429  rate limit (per-minute and per-day)
503  "This model is currently experiencing high demand"  UNAVAILABLE
```

0 successes in 12 consecutive attempts. Other Gemini models tested:
`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash` all return
`404 no longer available to new users`. `gemini-3.5-flash` answered a 19-token
prompt but returned 503 on a 7,000-token one.

One unproven signal: 503 only ever appeared at prompt sizes ≥ 6k tokens, while
smaller prompts returned 429. This may mean large prompts are shed first under
load, but the test was polluted by our own quota use and is not conclusive.

**Consequence:** the system must work fully locally. A design that depends on a
frontier model being available is not usable here.

---

## 3. The data: what `master.md` contains

Parsed with `yaml.safe_load` into typed objects. No model is involved in parsing.
Current contents:

```
16 projects
59 bullets           (max 3 printed per project, max 7 projects per CV)
58 skills            across 5 named lines (Frontend, Mobile, Backend, Testing, Infra)
30 skill_evidence    entries (skill -> years, level, and which projects prove it)
 8 gaps              (things the user cannot claim)
 3 titles            mobile | frontend | fullstack, each with a `use_when` rule
 2 degrees           M.S. Applied Computer Science; B.E. Computer Systems
 6 profile versions  (append-only; every edit is a new row)
```

The structure is already a graph:

```
SkillEvidence.evidence : list[project_id]    skill  -> projects that prove it
Project.bullets                              project -> bullets
Project.stack / tags                         project -> technologies
ClaimBoundary.cannot_claim                   project -> what it may NOT back
Gap.blocks                                   gap    -> what it rules out
Title.use_when                               title  -> when to use this framing
```

---

## 4. The flow as it stands

Two user actions. Timings are from live HTTP runs today, all on granite.

### Fit check — `POST /api/fit`

**Call 1 — read the posting.** Prompt: instructions + posting only. No profile,
deliberately: when the profile shared the context, extraction lost about a third
of the requirements.
Input: raw posting text. Output: `{company, role, seniority, location,
required_skills[{name, importance 1-3}], preferred_skills[...], years_required}`.
~1,800 tokens, 20–30 s.

**Call 2 — score it.** Prompt: instructions + a JSON slice of the profile
(skills, skill_evidence, project metadata, gaps, education — **no bullet text**)
+ the parsed requirements + the posting.
Output: `{score 1-10, reasoning, gaps[]}`. ~7,300 tokens, 35–80 s.

### Generate — `POST /api/generate`

Until today this was **one call** of ~9,100 tokens doing three jobs at once:
pick the title, rank all 16 projects, and fill in a coverage table. It is now
four smaller steps:

| Step | Who does it | Size | Time |
|---|---|---|---|
| 1. Pick the title | model, own call | ~1,700 tok | 1–11 s |
| 2. Pick which projects | **code**, no model | — | <1 ms |
| 3. Pick bullets within each project | model, one call per project | ~880 tok each | 4–6 s each |
| 4. Which requirements the page backs | **code**, no model | — | <1 ms |

Then, still in code:
- assemble the page from the real bullet text, by id
- **fill** if under 0.90 of a page (add spare bullets by relevance)
- **trim** if over 1.00 of a page (drop from the tail)
- check `required_qualifiers` and banned phrases, raise warnings
- render HTML → Chromium → PDF

Total for fit + generate, fully local: **90–150 seconds**. The user has stated
this is acceptable.

### Why step 2 and 4 are code, not model — the measurements

Each of these is three runs of the same posting (KEV, a junior full-stack role)
with identical input.

**Title, asked inside the big combined call:**
```
run 1  title='fullstack'      run 2  title='mobile'      run 3  title='frontend'
```
Three runs, three different answers, out of exactly three options.

**Title, asked alone in its own small prompt:**
```
profile order   fullstack  fullstack  fullstack
reversed        fullstack  fullstack  fullstack
mobile listed last  fullstack  fullstack  fullstack
```
9 of 9 correct, order-independent, ~1 s each. `fullstack` is right: the posting
asks for ASP.NET Core resolvers, Entity Framework and SQL.

**Bullets within one project, asked alone:**
```
run 1  hms-backend, hms-schema, hms-auth
run 2  hms-backend, hms-schema, hms-auth
run 3  hms-backend, hms-schema, hms-auth
```
3 of 3 identical, all valid ids.

**Which projects, asked as a 16-item menu (915 tokens, one line per project):**
```
run 1  hms, client-sites, tailor-tap, outreach-deck
run 2  dedicate, client-sites, tailor-tap, ratp-attendance-dashboard
run 3  hms, client-sites, amg-mvp, stanley-paden
```
Three runs, three different sets. `outreach-deck` and `amg-mvp` have **zero**
word overlap with this posting. This is why project choice was moved to code.

**Conclusion drawn:** this model is reliable on a small, local judgement and
unreliable at globally ranking many items — and it does not degrade gracefully,
it degrades silently and confidently.

### How code picks the projects

Greedy set cover. Each requirement in the posting has a weight (importance 1–3
for required, 1 for preferred). Each project covers the requirements whose words
appear in its bullets, stack or tags. Projects are chosen one at a time by how
much **new** weight they add to what is already chosen.

Simple top-N relevance was tried first and was wrong: for a posting wanting both
React and SQL it returned five front-end projects and left the database project
off the page entirely, because all five scored highly on the same React words.
Set cover put that project third instead of sixth.

---

## 5. What currently works, with numbers

Three real postings, end to end, fully local, no cloud model:

| Posting | Score | Title chosen | Projects | Requirements backed | Time |
|---|---|---|---|---|---|
| Invitation Project — Junior Fullstack | 8/10 | fullstack | 4 | **11 of 12** | 151 s |
| Government of Alberta — Junior Full Stack | 7/10 | fullstack | 4 | **13 of 14** | 124 s |
| KEV — Junior Software Developer | 8/10 | fullstack | 4 | **10 of 12** | 86 s |

For comparison, the same KEV posting through the old single-call design:
`mobile` title, **1** project (a React Native app, for a web role), **1 of 11**
requirements backed.

PDFs now come out at `page_count: 1`. Nothing fabricated appeared in any run.

---

## 6. Open bugs

### Bug 1 — the gaps list is wrong, and wrong in the dangerous direction

The scoring call returns a `gaps[]` array. It contains false entries that would
cause the user to skip jobs he is qualified for.

**Evidence A.** KEV requires: *"Working knowledge of at least one of: TypeScript
or JavaScript with React, or C# with .NET."* The user has 3.5 years of
professional React and TypeScript. The model returned:

```
gap: Missing required skill: Working knowledge of at least one of:
     TypeScript or JavaScript with React, or C# with .NET.
```

In the **same run**, the code-side coverage check marked that requirement
**backed**. Code right, model wrong, on identical input.

The scoring prompt already contains an explicit rule for this case:
> "Where the posting offers a choice, meeting either half meets it. 'TypeScript
> with React, or C# with .NET' is satisfied by React alone."

It was ignored.

**Evidence B.** The Government of Alberta posting asks for a two-year diploma.
The user holds an M.S. and a B.E. The model listed the diploma as a gap. The
code-side check (`_non_bullet()`) resolves degree requirements correctly from
the education section.

**Evidence C.** Earlier runs produced gaps for French and Django — neither
mentioned anywhere in the posting. The prompt explicitly forbids this:
> "If the posting does not ask for it, it is not a gap for this posting."

### Bug 2 — reasoning length is ignored

The prompt asks for "two or three sentences". Measured outputs: 7 sentences
(1,000 chars) and 11 sentences (944 chars). An earlier version produced eight
paragraphs written in the first person, as if the model were the candidate.

### Bug 3 — word-boundary matching misses obvious synonyms

Coverage and ranking match whole words only. So:

- `SQL` does not match `PostgreSQL`. KEV's "relational databases and SQL"
  reads unbacked against a bullet that says *"Designed the PostgreSQL schema
  behind it, with a 7-state visit lifecycle..."*
- `CI/CD` vs `GitHub Actions`, `cloud` vs `AWS Lambda`, and similar pairs fail.

Substring matching was tried and is worse: `cloud` matched `Cloudflare`, which
scored Azure as met when the user has never used Azure. That is the failure mode
this project most needs to avoid, so whole-word matching was kept deliberately.

### Bug 4 — run-to-run variance cascades

Extraction of the same posting varies between runs. Since code ranks projects
against the extraction, a different reading produces a different page.

```
Government of Alberta, run A:  13 of 14 backed, HMS on the page
Government of Alberta, run B:   8 of 13 backed, HMS absent
KEV title across three live runs:  fullstack, fullstack, frontend
```

Nothing invalid is ever produced — all ids are real — but the output is not
stable, and the user cannot tell which run is the good one.

### Bug 5 — required qualifiers are not printed

If a project appears on the page, its `required_qualifiers` must appear too.
The page-fill step adds projects without their qualifiers, producing warnings
such as:

```
"Stanley Paden" requires a qualifier that is not on the page:
    One E2E flow, iOS simulator only; Android E2E is configured but not enabled
"Dedicate" requires a qualifier that is not on the page:
    The 50% figure is estimated, not measured
```

The warning fires correctly. The qualifier is simply never placed on the page.
This is an honesty-guarantee leak, not a cosmetic issue.

---

## 7. Already tried and rejected — please do not re-propose these

| Idea | Why it was rejected |
|---|---|
| Use a frontier cloud model (GPT-4, Claude, Gemini Pro) | Gemini free tier returns 429/503 constantly; 0 of 12 attempts succeeded over two days. The tool must work offline on one laptop. Paid API is not currently on the table. |
| Preload the profile into the model so only the JD is sent | Models are stateless between calls. Fine-tuning can't track a weekly-changing profile. Prompt caching reduces cost, not what is sent. |
| Shrink the selection prompt so the 8B can handle it | Tested at 16, 8 and 5 projects (9,112 → 6,990 → 4,684 tokens). Title stayed wrong in 8 of 9 runs and it still picked 1–2 projects. Size was not the cause. |
| Let the local model score the fit on its own | With a truncated context it wrote a first-person essay claiming Azure experience, open-source contributions and authoring GraphQL APIs — none in the profile. |
| Score by counting word matches, no model at all | Built and measured. Scored 7/10 where a model said 1, and 3/10 where a model said 7. A posting asking for "AI capability" matched nothing and scored 1/10 for a job worth applying to. Deleted. |
| Retry Gemini on 503 | 0 of 12 attempts succeeded across two models. |
| Larger local model (qwen2.5:14b) | 100 s per extraction vs granite's 20–30 s, and 12 GB resident leaves the machine unusable. `mistral-nemo:12b` is pulled but untested. |

### One bug that is fixed, as context for how these usually go

ollama defaults `num_ctx` to **4096** regardless of what the model supports, and
truncates **from the front**, keeping the tail. granite3.3:8b supports 131,072.
We never sent `num_ctx`. So the 7,300-token scoring prompt and the 9,100-token
selection prompt arrived with the profile cut off and the posting intact.

That is why the model "invented" a title from posting text and scored a
candidate it had never seen. Sending `num_ctx: 12288` changed the score output
from an 8-paragraph fabrication to a 4-sentence assessment naming real gaps.
Several weeks of believing "the model cannot reason" were a config bug.

---

## 8. Questions we would like answered

1. **Gaps (bug 1) is the priority.** The plan is to compute met-vs-unmet in code
   from the profile graph — the same logic that already gets it right for
   coverage — and let the model only write the prose judgement about gaps it is
   handed. Is there a better approach that keeps a model's flexibility on
   requirements phrased as sentences ("experience designing and supporting
   modern full-stack applications") without letting it be wrong about plainly
   listed technologies?

2. **Semantic matching without false positives (bug 3).** We need `SQL` to match
   `PostgreSQL` but `cloud` not to match `Cloudflare`. Options considered: a
   hand-maintained alias table, a local embedding model with a similarity
   threshold, or asking the model per-requirement. Which is most robust, and
   what threshold or structure would you use? Cost matters: this runs per
   requirement per posting, around 12–14 requirements per posting.

3. **Variance (bug 4).** Is there a sound way to make a local 8B deterministic
   enough that the same posting gives the same CV? `temperature: 0`, seeds,
   self-consistency voting over N runs, or something else? N runs costs N × 20 s
   at 10 tok/s, so cheap methods are strongly preferred.

4. **Is four separate calls the right decomposition**, or is there a better one?
   We moved global ranking into code because the model could not do it. Is there
   a prompting structure that would let an 8B rank 16 items reliably — or is
   that simply beyond this model size?

5. **Model choice.** Is `granite3.3:8b` a good fit for this workload on 16 GB, or
   is there a better local model in the 7–14 B range for structured extraction
   and constrained id selection with enforced JSON schema output?

---

## 9. Stack, for reference

- Backend: Python 3.14, FastAPI, SQLModel on SQLite (WAL), Jinja + Playwright
  (Chromium) for the PDF. 299 tests.
- Frontend: Angular 20, standalone components, signals, Tailwind 4.
- Models called over HTTP with `httpx`. JSON shape enforced server-side via
  Gemini `responseSchema` / ollama `format`.
- Runs locally or in Docker. In Docker the app is containerised but ollama is
  not: Docker Desktop on macOS has no Metal/GPU access, so a containerised model
  would run on CPU.
- Single user, single password, binds to `127.0.0.1` only.
