"""
The starter profile and the Claude briefing that goes with it.

Both are content, not code, and both get reworded far more often than anything
around them. The defaults live here so a fresh checkout works with no config;
HIRED_PROFILE_TEMPLATE and HIRED_CLAUDE_BRIEFING override them, so rewording
either one is an environment change and a restart rather than a code change.
"""

from .settings import get_settings

DEFAULT_TEMPLATE = """# Identity
name: Your Name
location: City, Country
relocation: Open to relocation
email: you@example.com
phone: +1 000 000 0000
linkedin: linkedin.com/in/you
github: github.com/you
portfolio: yoursite.com
# Anything else you would put in a CV header. A bare URL is fine, or give it a label.
links:
  - Dribbble: dribbble.com/you
  - Stack Overflow: stackoverflow.com/users/0/you
authorization: Authorized to work in X, no sponsorship required

# Titles
# One headline per framing you apply under. The selector picks one per posting.
- id: fullstack
  text: Full-Stack Engineer | React · Node.js · TypeScript
- id: frontend
  text: Front-End Engineer | React · TypeScript · Design Systems

# Summaries
# Ids match the titles above. max_chars keeps it inside the layout.
- id: fullstack
  max_chars: 520
  text: >
    Two sentences on what you build and what you are good at. Written by you,
    never generated.
- id: frontend
  max_chars: 520
  text: >
    The same, framed for front-end roles.

# Skills
- line: Frontend
  items: [React, TypeScript, CSS]
- line: Backend
  items: [Node.js, PostgreSQL]
- line: Infra
  items: [Docker, GitHub Actions, AWS]
  # gated skills only reach the page when their evidence project does
  gated: [AWS]

# Experience
## Company Name
role: Your Role
location: Remote
start: 2024-01
end: present
priority: 1

### Project Name
label: One line on what the product is
stack: [React, TypeScript]
priority: 1
tags: [frontend, react]
links:
  - Live: product.example.com
  - Repo: github.com/you/project

# The claim boundary is the point of this file. Write it before the bullets.
claim_boundary:
  can_claim:
    - Something you did and can describe end to end
  cannot_claim:
    - Something adjacent that you did not do
  required_qualifiers:
    - 'Any number you quote must say where it came from'

bullets:
  - id: project-name-first
    priority: 1
    tags: [frontend, react]
    text: Verb-first sentence describing one thing you built. No first person.
  - id: project-name-second
    priority: 2
    tags: [react]
    text: A second bullet. Keep every claim inside the boundary above.

# Education
- school: University Name
  degree: BSc
  field: Computer Science
  location: City, Country
  start: 2018-09
  end: 2022-05

# Certifications
- name: Certification Name
  issuer: Who issued it
  date: 2023-04
  url: credly.com/badges/you

# Languages
- name: English
  level: Native
"""

# {template} is where the starter file is spliced in. Without the placeholder the
# template is appended at the end instead, so a briefing rewrite cannot lose it.
DEFAULT_BRIEFING = """I am filling in the "master profile" for a CV tailoring tool called hired. The tool builds a one-page CV for a specific job posting by *selecting* from bullets I have already written. It never writes new claims. So this file may only contain things I can defend in an interview.

Interview me one section at a time. Ask about my work history before anything else, since it is the bulk of the file. When we are done, output the finished file as one markdown code block I can copy back into the app.

Rules that matter more than completeness:

- Never invent a metric, a technology, or a responsibility. If I do not give you a number, do not add one. An empty field is fine; a plausible guess is not.
- Every project needs a claim_boundary, and cannot_claim is the important half: the adjacent things I did NOT do. Ask me for those explicitly, because I will forget to volunteer them.
- required_qualifiers holds wording that must always travel with a claim, for example that a figure is estimated rather than measured.
- Bullets are verb-first, no first person, one accomplishment each.
- Give every bullet and project a stable lowercase id with hyphens.
- Mark a bullet "status: blocked" if I say I cannot back it up yet.

Format rules, because the file is parsed strictly:

- Keep the section names, heading levels and field names exactly as they appear below.
- Section bodies are YAML. Any value containing a colon, or starting with a quote, must be wrapped in single quotes end to end.
- Leave out a field rather than filling it with a placeholder.

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
