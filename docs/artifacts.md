# Artifacts: the email and the answer

A CV is not the only thing a posting asks for. Wellfound wants a paragraph in a
box. A referral wants an email with the CV attached. A company portal wants
"why do you want to work here" in 500 characters. Today all of that means
leaving hired, opening Claude, and writing against a profile Claude cannot see.

This document is the design for generating those from the application you have
already scored. Written down because the feature has been discussed three times
and lost three times: it existed only in conversation, never in the repo.

## What it produces

Two kinds, both text, both attached to an application:

| Kind | Input | Output |
| --- | --- | --- |
| `email` | the application | subject line and ~120 words, to paste into a mail client with the CV attached |
| `answer` | the application + the question | prose sized to the question, to paste into a form |

Sending is out of scope. No SMTP, no credentials, no deliverability, no bounce
handling. hired writes the text; you copy it and attach the PDF the row already
holds.

## Where it lives

One home: the application detail page. Both routes reach it.

```
fit score ──┬── Generate a CV ─────→ CV ──→ detail ──┬── Write an email
            │                                         ├── Answer a question
            ├── Save without a CV ────────→ detail ───┘
            │
            ├── Skip this one            (status: skipped, not applying)
            └── Discard                  (nothing is written)
```

A fork on the fit screen that offered "answer" against "CV" was considered and
rejected: it is a second door to the same room, and the room is the detail page.

### The one new button

"Save without a CV" does not exist yet and cannot be faked with the button
beside it. The current "Keep, not applying" calls `save('skipped')`, and
`skipped` means a posting you decided against — it has its own pipeline segment
and it is excluded from the sent count. A Wellfound application is one you are
*pursuing*, so it must land in `saved`.

So: add "Save without a CV" (status `saved`), and rename "Keep, not applying"
to "Skip this one", which is what it has always done.

## How the text is produced

The reason AI writing reads as AI is not its vocabulary. It is that the model
has nothing specific to say and fills the space with register: *excited about
the opportunity, particularly drawn to, your innovative approach*. Telling it to
"sound human" produces the same paragraph with contractions in it.

So the model is not asked what to say. Code decides that, and the model only
decides how to phrase it. This is the same split that fixed the fit reasoning,
where output went from eleven fabricated sentences to three accurate ones the
moment the met/unmet lists were worked out in code and handed over.

Everything needed is already on the application row:

| Content | Where it comes from |
| --- | --- |
| company, role | `jd_parsed` |
| two or three strongest bullets | `selected_bullets`, ranked by `_relevance` |
| what the profile actually covers | `requirements()` met list, with the backing skill named |
| the honest gap, when there is one | `gaps` |

The model receives those and joins them. It may not introduce a fact. The
prompt is short, names the audience, and forbids the register directly rather
than asking for warmth.

Then `_check_banned` runs over the output. It already exists, already guards
the CV, and already reads `rules.banned_words` from the profile. It gains a
list of AI tells.

### Sounding like you

Built from your own bullet sentences, with your own numbers, it sounds like you
by construction. Nothing further is planned. If the first drafts read wrong,
the next step is a writing sample in the profile — the schema has nowhere to
put one today, and adding one before there is evidence is speculation.

## The honest limitation

This is the first artifact where a model writes prose that goes out under your
name.

The CV is safe structurally: the model returns bullet ids and never prose, so
inventing a claim is not a thing it can do. **That guarantee does not transfer
to an email.** The guards here are weaker and should be named rather than
discovered:

1. The content is chosen in code, so the facts come from the profile.
2. Banned phrases are checked after generation.
3. You read it before you send it.

That is a weaker promise than the CV makes, and the UI should not pretend
otherwise.

## Storage

A JSON column on `Application`, matching `coverage` and `selected_bullets`:

```python
artifacts: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
# {kind, question, subject, body, model, created_at}
```

No new table. These are read with their application and never queried across.

## Development plan

Each step ends somewhere usable, and each leaves a check behind.

### 1. Storage and the route

- `artifacts` column on `Application`, plus the `ALTER TABLE` on the live db
- `POST /api/applications/{id}/artifacts` taking `{kind, question?, model?}`
- `app/artifacts.py`: assemble the facts from the row, one `generate_json` call,
  `_check_banned` over the result, append to the row
- Honours the `pick` ContextVar like every other call, so the model picker works

**Check:** a test that the assembled prompt contains the selected bullets and the
company, and contains no sentence the model is free to invent around.

### 2. The fit screen buttons

- "Save without a CV" → `save('saved')` → navigate to the detail page
- Rename "Keep, not applying" to "Skip this one"

**Check:** a test that the new button writes `saved`, not `skipped`.

### 3. The detail page

- An "Artifacts" section: two buttons, a question input for `answer`
- Generated text in an editable textarea, with a copy button
- Model name shown beside each, as the CV and fit already do
- Saved artifacts listed, most recent first

### 4. Measure, then tune

Generate an email for three real postings. Read them as a recruiter would. The
prompt is wrong until the output is worth sending, and no amount of designing in
advance settles that — the fit reasoning took four rounds against real postings.

**Not in scope until asked:** cover letters, LinkedIn messages, follow-up
nudges, templates per platform, sending anything.
