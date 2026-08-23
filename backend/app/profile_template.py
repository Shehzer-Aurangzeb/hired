"""
The starter profile and the Claude briefing that goes with it.

Both are content, not code, and both get reworded far more often than anything
around them. The defaults live here so a fresh checkout works with no config;
HIRED_PROFILE_TEMPLATE and HIRED_CLAUDE_BRIEFING override them, so rewording
either one is an environment change and a restart rather than a code change.
"""

from .settings import get_settings

DEFAULT_TEMPLATE = """# Identity
# Everything that belongs in a CV header. Only `name` is required. Leave a
# field out entirely rather than filling it with a placeholder.
name: Your Name
location: City, Country
email: you@example.com
phone: '+1 000 000 0000'
linkedin: linkedin.com/in/you
github: github.com/you
portfolio: yoursite.com
# Any other header link. A bare URL works, or give it a label.
links:
  - Dribbble: dribbble.com/you
  - Stack Overflow: stackoverflow.com/users/0/you
  - label: Conference talk
    url: youtube.com/watch?v=example
# Printed only if you fill them in.
relocation: Open to relocation
authorization: Authorized to work in Canada, no sponsorship required

# Titles
# One headline per kind of role you apply to. Exactly one is printed per
# posting, chosen from this list. Two or three framings is usually enough.
- id: fullstack
  text: Full-Stack Engineer | React · Node.js · TypeScript
- id: frontend
  text: Front-End Engineer | React · TypeScript · Design Systems

# Summaries
# Ids match the titles above, one summary per title. Written by you, never
# generated. max_chars is what fits the layout; over it and you get a warning.
- id: fullstack
  max_chars: 520
  text: >
    Two or three sentences on what you build, what you are good at, and the kind
    of problem you want next. No metrics you cannot source.
- id: frontend
  max_chars: 520
  text: >
    The same person, framed for front-end roles.

# Skills
# One entry per row printed in the skills block, in the order you want it read.
- line: Frontend
  items: [React, TypeScript, RxJS, Tailwind CSS]
  # never_standalone: printed only next to something else in the same row, for
  # things you have used but would not want read as a headline skill.
  never_standalone: [RxJS]
- line: Backend
  items: [Node.js, Python, FastAPI, PostgreSQL]
- line: Infrastructure
  items: [Docker, GitHub Actions, AWS]
  # gated: only reaches the page when a project that evidences it is selected.
  gated: [AWS]

# Experience
# One `##` per employer, newest first. Everything between it and the first
# `###` describes the job; each `###` is one project inside that job.

## Company Name
role: Your Role
location: City, Country
start: 2024-01
end: present
# priority 1 means "always fit this on the page", 5 means "only if there is room".
priority: 1

### Project Name
# The heading becomes the project id (project-name) unless you set `id:` here.
label: One line on what the product is, for a reader who has never heard of it
stack: [React, TypeScript, Node.js]
priority: 1
tags: [frontend, react, design-system]
# disclosure: what you are allowed to say about this work in public.
disclosure: Client under NDA; describe as "a national retailer"
links:
  - Live: product.example.com
  - Repo: github.com/you/project

# The claim boundary is the point of this file. Write it before the bullets.
claim_boundary:
  can_claim:
    - Something you did and could walk through end to end at a whiteboard
    - A decision you made and can name the alternatives you rejected
  cannot_claim:
    - The adjacent piece on the same project that somebody else owned
    - The part you only reviewed
  required_qualifiers:
    - 'Any figure quoted must say where it came from, e.g. measured in Lighthouse CI'

bullets:
  - id: project-name-perf
    priority: 1
    tags: [frontend, performance]
    text: Verb-first sentence naming one thing you built and what changed because of it.
  - id: project-name-ci
    priority: 2
    tags: [tooling, ci]
    text: A second accomplishment. One idea per bullet, no first person.
  - id: project-name-migration
    priority: 3
    tags: [backend]
    # status: blocked keeps a true bullet in the file and off every CV, for
    # something you are not ready to be questioned on yet.
    status: blocked
    text: Something true that you cannot evidence today.

### Second Project
label: A smaller piece of work worth keeping on record
stack: [Python, FastAPI]
priority: 3
tags: [backend, api]
claim_boundary:
  can_claim:
    - The part you wrote
  cannot_claim:
    - The deployment and the on-call for it
bullets:
  - id: second-project-api
    priority: 2
    tags: [backend, api]
    text: One accomplishment is enough for a project you will rarely print.

## Earlier Company
role: Earlier Role
location: City, Country
start: 2021-06
end: 2023-12
priority: 3

### Earlier Project
label: What it was
stack: [JavaScript]
priority: 4
tags: [frontend]
claim_boundary:
  can_claim:
    - What you actually shipped here
  cannot_claim:
    - Anything from before you joined
bullets:
  - id: earlier-project-ship
    priority: 3
    tags: [frontend]
    text: Keep old roles thin. One or two bullets each.

# Education
- school: University Name
  degree: BSc
  field: Computer Science
  location: City, Country
  start: 2018-09
  end: 2022-05
  notes: Anything worth a line, such as a thesis or an award
  links:
    - Thesis: example.com/thesis

# Certifications
- name: Certification Name
  issuer: Who issued it
  date: 2023-04
  url: credly.com/badges/you

# Languages
- name: English
  level: Native
- name: French
  level: Professional working
"""

# {template} is where the starter file is spliced in. Without the placeholder the
# template is appended at the end instead, so a briefing rewrite cannot lose it.
DEFAULT_BRIEFING = """I am filling in the master profile for a CV tailoring tool called hired. Interview me, then produce the finished file. Read all of this before you ask your first question.

## What this file is

hired builds a one-page CV for a specific job posting by *selecting* from what is already in this file. It never writes a new claim, never rounds a number up, and never invents a responsibility to match a posting. This file is the only place my claims come from, so everything in it has to be something I can defend in an interview.

That makes it not a CV. It is bigger than one: it holds every framing, project and bullet I might ever want to print, plus an explicit record of what I must NOT claim. The tool picks a subset per posting and the record of what is off limits is what keeps that subset honest.

## Your job

Interview me section by section, in the order the template gives. One question at a time, and wait for the answer. Do not send me a wall of questions and do not fill a section in on my behalf to keep things moving.

Work history is the bulk of the file, so budget most of the conversation for it: one pass per employer, then one pass per project inside that employer.

When an answer is vague, push once. "Improved performance" is not a bullet. Ask what was slow, what I changed, and how I know it got better. If I cannot say how I know, that is also an answer — see the blocked rule.

## Rules that matter more than finishing

1. Never invent anything. Not a metric, not a technology, not a scope. If I do not give you a number, the bullet has no number in it. An empty field is correct; a plausible guess is something I have to defend in a room.
2. Every project needs a claim_boundary, and cannot_claim is the important half. Ask me directly: what sat next to this that you did not do? Who owned the part you didn't? Where would you sink if the interviewer went one level deeper? I will not volunteer these, so you have to ask for them.
3. required_qualifiers is wording that must always travel with a claim — that a figure was estimated rather than measured, that a launch was a pilot, that "a team of eight" was four engineers and four others.
4. Put status: blocked on any bullet that is true but that I cannot evidence yet. It stays in the file and stays off every CV. Reach for it whenever I hesitate, instead of dropping the bullet or softening it.
5. One accomplishment per bullet. Verb-first, no first person, never "responsible for". Say what changed, not what I was assigned.
6. Ids are lowercase with hyphens and never change, because a generated CV points back at them. Prefix a bullet id with its project id.

## Getting the work history out of me

For each employer: role, dates, location, and then which projects are worth having on record at all — including ones I would only ever print for one kind of posting.

For each project, in this order:
- what the product was, in one line a stranger would understand
- the stack I personally worked in, not the company's whole stack
- what I am allowed to say in public: client names, NDAs, anything I have to describe generically
- the claim boundary, before any bullets exist
- then three to six bullets, hardest evidence first

Tag projects and bullets with the kinds of role they serve — frontend, backend, platform, data, leadership. The tags are how the selector finds them later, so reuse the same words across projects rather than inventing a new one each time.

## Format, because the file is parsed strictly

- Keep every section name, heading level and field name exactly as the template has them: # for a section, ## for an employer, ### for a project.
- Section bodies are YAML. Wrap any value containing a colon, or starting with a quote, in single quotes end to end.
- Dates are YYYY-MM, or `present` for a current role.
- Omit a field rather than writing a placeholder or "N/A" into it.
- priority is 1 to 5, where 1 means fight for it on the page.

## Output

When we are done, give me the complete file in a single markdown code block with no commentary inside it, ready to paste straight back into the app. Output every section in full even if the conversation ran long — never abbreviate one as "unchanged from above".

Here is the template to fill in, and the exact shape to return:

{template}"""


def template() -> str:
    return get_settings().profile_template or DEFAULT_TEMPLATE


def claude_prompt() -> str:
    briefing = get_settings().claude_briefing or DEFAULT_BRIEFING
    text = template()
    return (
        briefing.replace("{template}", text)
        if "{template}" in briefing
        else f"{briefing}\n\n{text}"
    )
