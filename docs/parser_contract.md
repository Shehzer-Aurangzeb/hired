# master.md parser contract

What `backend/app/profile_parser.py` and `backend/app/models.py` actually do.
Written for whoever changes the parser, not for the person writing a profile.

Where this document and the code disagreed, the code won and this was corrected:
the parser predates the contract. Everything below is pinned by a test.

---

## Grammar

The file is markdown headings wrapping YAML bodies. Three heading levels carry
meaning and nothing else does.

```
#   section     matched against a closed vocabulary
##  employer    user-named, only meaningful inside # Experience
### project     user-named, inside # Experience or # Projects
```

A heading's body runs to the next heading **of exactly that level**. That is why
a `##` does not end a `# Section` body and a `###` does not end a `##` body: each
level is split separately, on its own pass.

### The closed section vocabulary

```
Meta, Identity, Titles, Summaries, Skills, Skill Evidence, Experience,
Projects, Education, Certifications, Publications, Awards, Languages,
Availability, Gaps, Rules
```

Sixteen names, and the tuple order is the order a file should be written in.
`skill evidence` is two words in the heading and becomes `skill_evidence` on the
way into the model.

**A line starting with `#` at column zero is a section heading only if the text
after the hash matches this list, case-insensitively, after trimming. Otherwise
it stays in the body, where YAML reads it as a comment.**

This rule exists because annotated templates put explanatory comments at column
zero, and YAML comment syntax is identical to a markdown H1. Without the closed
vocabulary a naive split on `^#` creates a section called "Everything that
belongs in a CV header", and silently orphans everything under it.

The cost of a closed vocabulary is that `# Experiance` would be swallowed as a
comment and the whole work history would vanish without a word. So a rejected
heading is run through `difflib` at cutoff 0.75, and a near miss raises rather
than passing: `Unknown section "# Experiance". Did you mean "# Experience"?`

`##` and `###` are user-named and cannot be vocabulary-matched, so they are
recognised structurally. A `###` inside `# Experience` attaches to the preceding
`##`. A `###` inside `# Projects` lands in `Profile.projects`, **its own list —
there is no synthetic employer.** A company that does not exist has no business
appearing on a CV, and the two lists share one project id namespace, so nothing
downstream needs them merged.

### Normalization, before anything is split

- A leading BOM is stripped. It makes the first `# Identity` invisible to the
  heading match.
- `\r\n` and `\r` become `\n`. Otherwise every parsed value keeps a trailing `\r`.
- **Every** column-zero `---` is blanked. It is a horizontal rule to the person
  writing and a document separator to YAML, and `safe_load` refuses a stream
  holding two documents. Blanked rather than deleted, so line numbers in error
  messages still point at the line the person typed.

### YAML bodies

Parsed with `yaml.safe_load`, one call per body. A syntax error is reported
against the file line, not the line within the section:

```
# Titles is not valid YAML: mapping values are not allowed here.   (line 34)
```

A section that must hold a list and holds a mapping instead is an error rather
than silently empty, which would read as "I wrote nothing".

### Ids

- Project id is the `id:` field when present, otherwise the `###` heading
  slugified: lowercased, runs of non-alphanumerics to single hyphens, leading and
  trailing hyphens stripped.
- Bullet ids are authored, never derived.
- Ids are stable across regenerations. A generated CV records the bullet ids it
  used, so a changed id orphans history.

Duplicate project ids and duplicate bullet ids are **errors**, and the project
namespace spans Experience and Projects together: a bullet id resolves to one
project, so the same project id in both lists is ambiguous, not merely repeated.

---

## Section shapes

| Section | Shape | Printed |
|---|---|---|
| Meta | mapping | no |
| Identity | mapping | yes |
| Titles | list of mappings | one per CV |
| Summaries | list of mappings | one per CV |
| Skills | list of mappings | yes |
| Skill Evidence | list of mappings | no |
| Experience | employers, each with projects | yes |
| Projects | projects only | yes |
| Education | list of mappings | yes |
| Certifications | list of mappings | earned only |
| Publications | list of mappings | yes |
| Awards | list of mappings | yes |
| Languages | list of mappings | yes |
| Availability | mapping | no |
| Gaps | list of mappings | no |
| Rules | mapping | no |

Every section may be absent, and an absent one parses as empty rather than as an
error. `# Identity` is the exception: without it there is nothing to generate.

Within an entry a few fields are structurally required, because an entry without
them is not an entry:

```
Identity.name      Title.id, .text        Summary.id, .text
SkillLine.line, .items                    SkillEvidence.name
Project.id, .name  Bullet.id, .text       Experience.name
Education.school   Certification.name     Publication.title
Award.name         Gap.skill              Language.name
```

Everything else is optional with a default. `Certification.status` defaults to
`earned` on purpose: a file written before that field existed has no status, and
its certifications were real.

Every date field is `Str = Annotated[str, BeforeValidator(str)]`. YAML turns
`2024-11-01` into a `date` object, and the string form is what the layout wants.
`2024-11` and `present` are already strings and pass through untouched.

---

## Enumerations

```
employment_type   full-time, part-time, contract, freelance, internship, volunteer
status (project)  live, shipped, internal, pilot, sunset, abandoned
status (cert)     earned, in_progress, expired
status (bullet)   active, blocked
level             familiar, working, advanced, expert
context           professional, personal, academic
metric.source     measured, estimated, reported, none
gap status        none, learning, personal-only, rusty
language level    native, fluent, professional, conversational, basic
publication type  talk, article, paper, patent, book, podcast
```

**None of these are constrained in Pydantic.** A value outside its set is a
warning naming the allowed values, and the profile still saves. `Bullet.status`
is the one that branches code, and it is a plain string with an `active` default
for the same reason.

An empty value is not a wrong one. Every field is optional, so unwritten must
never read as invalid.

`priority` and date format are **not validated at all**. Any integer and any
string are accepted.

---

## Validation

Two severities, and the split is deliberate rather than a judgement about
importance.

**Errors** block the save. **Warnings** surface in the editor and let the save
through.

The profile row is the only copy of the CV data, so refusing a save costs more
than almost anything it could protect against. Errors are therefore limited to
files that cannot be turned into a `Profile` at all. Everything else is a
warning, and these get promoted the day a generator exists and there is
something concrete to protect.

### Errors — the complete list

| Check | Message shape |
|---|---|
| YAML syntax error in a section body | names the section and the file line |
| No `# Identity` section | `No "# Identity" section. Every profile needs one.` |
| A section heading appears twice | `"# Titles" appears twice. Merge the two into one.` |
| A near miss on a section name | `Unknown section "# Experiance". Did you mean "# Experience"?` |
| A list section holding a mapping | `"# Titles" must be a list. Start each entry with "- ".` |
| A required field missing from an entry | `experience -> 0 -> projects -> 0 -> id: Field required` |
| Duplicate project id, across both lists | `duplicate project id: shared` |
| Duplicate bullet id, across both lists | `duplicate bullet id: same` |

Validation is **fail-fast**: one error at a time, because YAML is fail-fast and
collecting more would mean re-parsing after each guessed fix.

### Warnings — the complete list

| Check | Why |
|---|---|
| Project with no `claim_boundary` at all | The guard cannot protect what has no boundary |
| Project with bullets but an empty `cannot_claim` | It is the half that protects you |
| No projects anywhere | Nothing to select from |
| Bullet text contains a digit and no `metric` | A number needs a source you can name |
| `metric.source: estimated`, "estimated" absent from the text | The qualifier has to travel with the claim |
| `status: blocked` with no `blocked_reason` | Nobody can act on it later |
| `status: blocked` with empty text | Defeats the unblock mechanism |
| Em dash or en dash on a line | Hard formatting rule. Carries the line number |
| A word from `rules.banned_words` in a bullet | The user set the rule |
| Skill in Skill Evidence in no Skills row | Probably a typo; nothing will match it |
| `gated: true` with empty `evidence` | The gate can never open, so it never prints |
| Project id in `evidence` that does not exist | Stale reference after a rename |
| Enum value outside its set | Names the allowed values |
| Employers not in descending `start` order | Print order will surprise you |
| Gaps section empty | Fit scoring degrades to guessing |
| Summary over `max_chars` | Layout will overflow |

The list is capped at **20**, and the tail collapses into one
`and N more, hidden so this list stays readable.` A hundred warnings and none
are the same thing to the person looking at them.

Warnings are advisory and nothing is auto-fixed. Silent correction of somebody's
profile is how a tool loses trust.

### `ProfileSummary`

Counts the editor shows beside the warnings.

```
projects            projects under an employer
projects_total      including the standalone Projects section
bullets             across both lists
blocked             bullets with status: blocked
missing_boundaries  projects with no claim_boundary
skills_evidenced    Skill Evidence entries
gaps                Gaps entries
unverified          unverified notes across all projects
```

---

## Where the file lives

Not on disk. The markdown is one row in the `profile_source` table, constrained
to `id = 1`. A container filesystem is wiped on redeploy and this is the only
copy of the CV data.

`GET /api/profile` re-parses that row per request — a 30KB document is
sub-millisecond, so there is no cache and therefore no cache to invalidate.
`parse(path)` exists for tests and fixtures only.

---

## Not built yet

Everything below describes the generator, which does not exist. It is kept here
because it is the design the parser was shaped for, not because any of it runs.

### Selection contract

**Excluded from the candidate pool before selection runs:**
- Any bullet with `status: blocked`
- Any certification without `status: earned`
- Any gated skill whose `evidence` projects are not on the page

**The selector returns bullet ids only, never bullet text.** This is the
structural guarantee. A model that can only point at existing content cannot
invent content. Every other honesty mechanism in the file is a policy the model
could theoretically violate. This one it cannot.

**After selection, before rendering, the claim guard checks:**
- Every returned id exists and is not blocked
- Every `required_qualifier` on a selected project appears in the rendered output
- No banned word or character survived
- No sentence was produced that is not either a bullet `text`, its `short`
  variant, or a Summary

**Gaps are reported, never covered.** If a posting requires something no bullet
evidences, the response carries it in a `gaps` array. It does not stretch a
nearby bullet to reach.

### Line budget

The one-page loop, in order, before it touches typography:

1. Drop Education `coursework`, then `gpa`
2. Swap a priority 1 bullet for its `short` variant, longest first
3. Drop the lowest-priority bullet across all selected projects
4. Drop the lowest-priority project once it holds one bullet
5. Drop the employer `context` line
6. Drop `relocation` from the header

Never below 10pt, never below 0.5in margins, never below 1.0 line height. After
five passes, return the draft with a warning rather than degrading the layout.

### Checks the contract asked for that nothing implements

Listed so they are not mistaken for working, and so the reasoning survives:

- **A fenced ` ```yaml ` body.** The contract asked for it because Claude fences
  by habit. It is a hard parse error today, and a cryptic one: `found character
  '`' that cannot start any token`. The briefing tells Claude to return the file
  in a markdown code block, so a person who copies the fence along with the
  contents hits this.
- **Employer ids.** Employers are keyed by their heading text.
- **Bullet id prefixed with its project id.** A convention the briefing asks for,
  enforced nowhere.
- **Malformed dates.** Any string is accepted.
- **`priority` outside 1 to 5.** Any integer is accepted.
- **Summary id with no matching Title id.**
- **Project with no bullets, employer with no projects.**
- **More than five Titles.**
- **First-person pronouns, non-verb openers, bullets over ~240 characters.**
- **Tags outside a shared vocabulary.** There is no shared vocabulary yet.
- **Missing `compensation` in Availability.**
