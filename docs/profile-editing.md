# Editing the profile inside hired

Status: agreed, not built. Written 2026-10-07.

## The problem

master.md is the product. The CV, the fit score and the coverage report are all
views over it. But the file is authored in Claude and pasted in, so the app owns
the most valuable artefact in the system without owning the means to maintain it.

That has three costs:

- The profile only improves when a session with Claude gets scheduled.
- Every update risks a full-file regeneration, so small changes feel expensive.
- The part that decays fastest, what you have used recently, is the part that is
  hardest to update.

Evidence from 61 applications on file: 36 of 54 skills have no `skill_evidence`
entry. Redux was asked for in three postings and backed by a printed bullet in
none, and one fit check reported it as a gap because the profile could not
verify depth. Libraries that are missing from the file entirely (i18next,
Apollo, Jotai, GSAP, Firebase analytics, MySQL, PHP) read to the model as skills
the candidate does not have.

## The insight

The reason the interview happens in Claude is not that typing is hard. It is
that the hard part is being interrogated.

A form would accept a project with an empty `cannot_claim`. The interview will
not: it asks what the project would fail to prove to a skeptical interviewer,
and keeps asking. That question is the whole value of the file.

So the in-app editor is a conversation, not a form. Forms are for data entry.
This is an interview.

## Principles

1. **The file stays the source of truth.** No migration to a table of fields.
   Markdown is the thing and every editor is a view over it. It stays portable,
   diffable and readable, and the raw tab is always the escape hatch.

2. **The model proposes, it never writes.** Same shape as the CV selector, which
   returns ids rather than prose because a model that cannot write prose cannot
   invent a claim. Here the model returns a proposed patch, the app renders it
   as before and after, and nothing lands until it is approved. Every proposal
   passes `validate_text` first, so an unparseable file cannot be saved.

3. **Honesty constraints can only tighten on their own.** The model may add to
   `cannot_claim`, `required_qualifiers`, `gaps`, and may block a bullet. It may
   never loosen one. Removing a `cannot_claim`, unblocking a bullet or deleting a
   gap is a hand edit. The profile can get more honest by itself and only ever
   gets bolder deliberately.

4. **Nothing is irreversible.** Version history is a prerequisite, not a
   nice-to-have. Nobody lets a model near their most important document without
   undo.

5. **Validation is live.** `validate_text` already exists and already returns
   line numbers. Surface it inline rather than on save.

## The three surfaces

### A. Ask

A box on the profile page. Plain language in:

> I used Redux on Union AI and Stanley Paden

It works out the section, drafts the YAML, shows the diff, waits for approval.
No section picker, no schema knowledge. This is the surface that removes the
round trip to Claude.

### B. Needs attention

The app can already compute what is thin:

- skills with no `skill_evidence` entry
- projects with an empty `cannot_claim`
- bullets containing a digit with no `metric` block
- `last_used` dates going stale
- blocked bullets nobody has revisited

Ranked list, each row starting a two-question interview. Turns "go fix your
profile" into a finite list that visibly shrinks.

### C. Harvest during the fit check

When a posting asks for something the profile records thinly, ask in the moment,
while the context is already in the reader's head:

> Pelmorex wants Redux. You list it with no evidence. Which projects used it?
> [Union AI] [Stanley Paden] [neither] [skip]

One tap. The profile improves as a side effect of applying, which means no
separate maintenance session ever again.

## Build order

1. **Version history.** Nothing else is safe without it.
2. **Ask, with diff approval.** Kills the Claude round trip.
3. **Needs attention.** Pays off the 36 empty skill entries.
4. **Harvest during the fit check.** The part that makes it a product.

## Deliberately out of scope

The cold-start interview stays in Claude. It is forty questions and an hour, it
happens once, and `DEFAULT_BRIEFING` already does it well. Rebuilding it in-app
is weeks of work to replace something that works. Build for the next five years
of the file, not its first hour.

---

# 1. Version history

Status: discussed, not built.

## Why first

Every later feature puts a model near the only copy of the CV data. Approval
before a write prevents a bad patch from landing. Version history is what
recovers from the bad patch that gets approved anyway, by a tired person at
11pm who clicked yes.

It is also independently useful: the file is edited by hand today, and there is
currently no undo at all.

## What exists now

`profile_source` is a single row, pinned by `CheckConstraint("id = 1")`, holding
`text` and `updated_at`. `updated_at` doubles as an optimistic lock: a save
carrying a stale `expected_updated_at` is refused with a 409.

Saving overwrites `text` in place. The previous content is gone.

`tools/backup.py` writes a dated `master-<stamp>.md` beside the database copy,
but that runs on a timer and keeps 14 days. It is disaster recovery, not undo.

## The agreed design

**An append-only log in `profile_source`. The newest row is the profile.**

Each row is one version. Nothing is ever updated in place; the only write is an
insert. That matches what `application` already does, where the printed bullet
text is copied onto the row rather than referenced, so history survives.

### Schema

The `CHECK (id = 1)` constraint goes, and `id` becomes `AUTOINCREMENT`.

| column | notes |
|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT`. The version number, shown as v1, v2. |
| `text` | the whole file, as typed |
| `updated_at` | when this version was written, and still the optimistic lock |

No `active` column. **Active is `max(id)`**, which is derivable, so it cannot
disagree with itself: there is no way to end up with two rows marked active or
none.

No `source` or `author` column yet. When Ask lands, "did a model write this"
becomes worth recording, and `ALTER TABLE ADD COLUMN` is cheap in SQLite.

### Why AUTOINCREMENT, and not a separate version column

SQLite picks the next rowid as one past the highest **surviving** row, so a
deleted id gets handed out again. Demonstrated:

    after 5 inserts:    1:a  2:b  3:c  4:d  5:e
    after pruning 4,5:  1:a  2:b  3:c
    after one save:     1:a  2:b  3:c  4:brand new save

Id 4 meant two different documents. That matters because a version number
crosses a boundary: the browser reads it, holds it, and sends it back when
someone clicks restore. An identifier that changes meaning in between restores
the wrong document.

`AUTOINCREMENT` makes SQLite keep a high-water mark in `sqlite_sequence` and
never reuse a number, even if the newest row is deleted.

A separate `version` column set to `max(version) + 1` carries the same bug, and
is only safe because the prune rule keeps the newest row. That couples its
correctness to a policy living in other code. The database's own guarantee is
better than our policy.

Pruning leaves gaps in the numbering (v1, v2, v7, v8). That is honest.

### Saving

Every save writes a new version. No prompt.

The Edit tab has no autosave: `canSave` requires the buffer to be dirty and the
profile to validate, and the person clicks Save. The intent is already
explicit, so asking "save this as a version?" afterwards is a second
confirmation for the same decision, at the moment it is least welcome.

### Restore

Restoring v5 appends its text as a new version. It never rewinds.

Rewinding would delete the record of the mistake, and makes "restore twice"
ambiguous. Appending keeps the log honest: you can see that a restore happened.

### Pruning

Runs inside the save transaction, because saving is the only moment a row is
created. Not at server start: this server runs for weeks, so it would rarely
fire when it matters, and it would add a way for boot to fail over housekeeping
nobody is waiting on.

    INSERT the new version
    DELETE versions older than 60 days
      EXCEPT the newest 5
      EXCEPT the active one

Both exceptions matter. Time alone would delete everything after a 61 day
break, including the version in use, leaving no undo at exactly the moment it
is wanted.

Consequence worth knowing: if nobody saves for a year, nothing prunes and old
versions sit past 60 days. Harmless, and they go on the next save, but the UI
says "versions are kept for 60 days" and briefly that is not literally true.

### Concurrency

Unchanged. `updated_at` stays the optimistic lock. A tab holding v20's
timestamp that saves after a restore created v21 gets the existing 409.

Old versions are read-only for free: nothing ever updates a row.
