# Meta
  # schema_version lets the parser migrate old files. Do not remove it.
  # Every line in this file that begins with # at column zero is either one of the
  # sixteen section names listed below, or the parser treats it as a comment.
  # Comments inside a section body should be indented, as these are.
schema_version: 1
updated: 2026-08

  # The sixteen sections, in required order:
  #   Meta, Identity, Titles, Summaries, Skills, Skill Evidence, Experience,
  #   Projects, Education, Certifications, Publications, Awards, Languages,
  #   Availability, Gaps, Rules
  # Sections may be empty but the heading should still be present.
  # Meta, Skill Evidence, Availability, Gaps and Rules are never printed on a CV.
  # They exist so the tool can score fit honestly and refuse to overclaim.

---

# Identity
  # Header content only. Anything that is a constraint rather than a printed line
  # belongs in Availability instead. Only name is required.
  # Omit a field entirely rather than writing a placeholder into it.
name: Your Name
location: City, Country
email: you@example.com
phone: '+1 000 000 0000'
linkedin: linkedin.com/in/you
github: github.com/you
portfolio: yoursite.com
links:
  - label: Stack Overflow
    url: stackoverflow.com/users/0/you
  - label: Conference talk
    url: youtube.com/watch?v=example
  # Printed only if present. Leave out if it does not help you.
relocation: Open to relocation
authorization: Authorized to work in Canada, no sponsorship required

---

# Titles
  # One headline per kind of role you apply to. Exactly one is printed per posting.
  # use_when is not printed. It tells the selector when this framing wins.
  # Two to four framings is usually enough. More than five means they overlap.
- id: fullstack
  text: 'Full-Stack Engineer | React · Node.js · TypeScript'
  use_when: Posting asks for backend ownership, API design, or database work.
- id: frontend
  text: 'Front-End Engineer | React · TypeScript · Design Systems'
  use_when: Posting is front-end only. Default when nothing else fits.

---

# Summaries
  # One per title id. Written by you, never generated from your bullets.
  # Write these last, after every project is in the file. A summary written
  # before the evidence exists always overclaims.
  # max_chars is what the layout fits. Over it and you get a warning, not a crash.
- id: fullstack
  max_chars: 520
  text: >
    Two or three sentences on what you build, what you are good at, and the kind
    of problem you want next. No metric that is not already in a bullet below.
- id: frontend
  max_chars: 520
  text: >
    The same person, framed for front-end roles.

---

# Skills
  # One entry per row printed in the skills block, in reading order.
  # Put the row a recruiter should see first at the top.
  # Four to five rows is the practical maximum for a one-page CV.
- line: Frontend
  items: [React, TypeScript, RxJS, Tailwind CSS]
  # never_standalone: printed only alongside something else in the same row.
  # For things you have used but would not want read as a headline skill.
  never_standalone: [RxJS]
- line: Backend
  items: [Node.js, Python, FastAPI, PostgreSQL]
- line: Infrastructure
  items: [Docker, GitHub Actions, AWS]
  # gated: reaches the page only when a project evidencing it is also selected.
  # Use this for anything you have done once, on a personal project, or in study.
  gated: [AWS]

---

# Skill Evidence
  # Never printed. This is how the tool answers "5+ years of React required"
  # without guessing, and how it refuses to claim a gated skill.
  # You do not need an entry for every skill. Write one for:
  #   - anything a posting is likely to filter on
  #   - anything listed as gated above
  #   - anything where your real depth is lower than the row implies
  #
  # level is one of: familiar, working, advanced, expert
  #   familiar  used it, would need the docs open, do not want a deep question on it
  #   working   shipped it to production, can answer normal questions confidently
  #   advanced  primary tool, can make architecture calls and defend the rejected options
  #   expert    colleagues ask you, you know the failure modes and the internals
  #
  # context is one of: professional, personal, academic
  # evidence lists project ids from Experience or Projects that prove it.
- name: React
  years: 4
  last_used: 2026-08
  level: advanced
  context: professional
  evidence: [project-name, second-project]
- name: AWS
  years: 0.5
  last_used: 2026-07
  level: familiar
  context: personal
  evidence: [side-project]
  gated: true

---

# Experience
  # One ## per employer, newest first. Everything between the ## and the first ###
  # describes the job. Each ### is one project inside that job.
  # A ### heading always means a project, in this section and in Projects below.

## Company Name
role: Your Role
location: City, Country
start: 2024-01
end: present
  # employment_type is one of: full-time, part-time, contract, freelance,
  # internship, volunteer. It is printed only when it is not full-time,
  # because omitting a contract or volunteer arrangement reads as a lie later.
employment_type: full-time
  # context: one line on the employer, printed above the projects when there is room.
context: Small founder-led engineering team building client products.
  # previous_roles: only if you were promoted. Newest first, excluding your current one.
previous_roles:
  - role: Junior Engineer
    start: 2024-01
    end: 2025-03
  # disclosure: what you may say about this employer in public. Not printed.
disclosure: Client names may be used; contract terms may not.
priority: 1

### Project Name
  # The heading becomes the project id (project-name) unless you set id: here.
  # Ids never change once written, because generated CVs point back at them.
label: One line on what the product is, for a reader who has never heard of it
stack: [React, TypeScript, Node.js]
  # my_role: your actual scope, in the words you would use under questioning.
  # "Front-end lead on a team of ten" and "one of six contributors" are both fine.
  # "Led the project" when you did not is the thing this field exists to stop.
my_role: Front-end lead on a team of ten
start: 2024-02
end: 2025-06
  # status is one of: live, shipped, internal, pilot, sunset, abandoned
status: live
  # domain: the industry, for matching postings. One or two words.
domain: fintech
  # named: false prints this project's bullets straight under the employer with
  # no bold lead-in of its own. For small pieces of client work where naming each
  # one costs more lines than the work is worth. Defaults to true.
named: true
priority: 1
tags: [frontend, design-system, performance]
  # disclosure: what you are allowed to say about this work in public.
disclosure: Client under NDA; describe as "a national retailer"
links:
  - label: Live
    url: product.example.com
  - label: Repo
    url: github.com/you/project

  # The claim boundary is the point of this file. Write it before any bullet.
  # cannot_claim is the half that protects you. If it is empty, you have not
  # thought about the project hard enough yet.
claim_boundary:
  can_claim:
    - Something you could walk through end to end at a whiteboard
    - A decision you made, where you can name the options you rejected and why
  cannot_claim:
    - The adjacent piece on the same project that somebody else owned
    - The part you reviewed rather than wrote
    - What this project does not prove, such as scale it never had
  required_qualifiers:
    # Wording that must travel with a claim every time it is printed.
    - 'Any figure quoted must say where it came from, e.g. measured in Lighthouse CI'
    - 'The team of eight was four engineers and four non-engineers'
  # unverified: true things you cannot evidence today. Each one should have at
  # least one bullet below carrying status: blocked and pointing at it.
unverified:
  - Whether the in-app purchase library was ever wired up. Check package.json.

bullets:
  - id: project-name-perf
    priority: 1
    tags: [frontend, performance]
    text: Verb-first sentence naming one thing you built and what changed because of it.
    # short: an alternative wording used when the page is one line too long.
    # Same claim, fewer words. Optional, and worth writing for priority 1 bullets.
    short: A tighter version of the same accomplishment.
    # metric: fill this in whenever the text contains a number.
    # source is one of: measured, estimated, reported, none
    #   measured   you saw it in a tool and can name the tool
    #   estimated  you worked it out from what you know, and the word
    #              "estimated" must appear in the text above
    #   reported   somebody else measured it, and the qualifier names them
    # A number with no metric block is a validation error.
    metric:
      value: '40% faster first contentful paint'
      source: measured
      method: Lighthouse CI, comparing the release before and after
  - id: project-name-ci
    priority: 2
    tags: [tooling, ci-cd]
    text: A second accomplishment. One idea per bullet, no first person.
  - id: project-name-migration
    priority: 3
    tags: [backend]
    # status: blocked keeps a true bullet in the file and off every CV.
    # Use it whenever you hesitate, instead of dropping the bullet or softening it.
    status: blocked
    blocked_reason: Cannot evidence the before number without access to the old dashboards.
    text: Something true that you cannot evidence today, written in full.

### Second Project
label: A smaller piece of work worth keeping on record
stack: [Python, FastAPI]
my_role: Sole engineer
priority: 3
tags: [backend, api-design]
claim_boundary:
  can_claim:
    - The part you wrote
  cannot_claim:
    - The deployment and the on-call rotation for it
  required_qualifiers: []
bullets:
  - id: second-project-api
    priority: 2
    tags: [backend, api-design]
    text: One accomplishment is enough for a project you will rarely print.

## Earlier Company
role: Earlier Role
location: City, Country
start: 2021-06
end: 2023-12
employment_type: full-time
priority: 3

### Earlier Project
label: What it was
stack: [JavaScript]
my_role: One of four engineers
priority: 4
tags: [frontend]
claim_boundary:
  can_claim:
    - What you actually shipped here
  cannot_claim:
    - Anything that shipped before you joined
  required_qualifiers: []
bullets:
  - id: earlier-project-ship
    priority: 3
    tags: [frontend]
    text: Keep old roles thin. One or two bullets each.

---

# Projects
  # Work that is not attached to an employer. Personal builds, open source,
  # freelance done outside a contract, academic work worth printing.
  # Same shape as a project inside Experience. Still uses ###.
  # This is usually where a gated skill earns its evidence, so be strict here:
  # a personal project proves you can build the thing, not that you have run it
  # in production, and cannot_claim is where you say so.

### Side Project
label: What it is, in one line
stack: [Next.js, PostgreSQL, AWS]
my_role: Solo
start: 2026-03
end: present
status: live
  # why_built: not printed, but it is the answer when an interviewer asks.
why_built: Needed it myself and wanted a reason to learn the infrastructure side.
priority: 3
tags: [fullstack, infra]
links:
  - label: Repo
    url: github.com/you/side-project
claim_boundary:
  can_claim:
    - Built and deployed it end to end
  cannot_claim:
    - Users, traffic, uptime or any operational track record
    - That the infrastructure has ever been under load
  required_qualifiers: []
bullets:
  - id: side-project-infra
    priority: 3
    tags: [infra]
    text: What you built, named specifically enough to be questioned on it.

---

# Education
- school: University Name
  degree: BSc
  field: Computer Science
  location: City, Country
  start: 2018-09
  end: 2022-05
  # gpa and coursework are omitted from the page by default. They are here so
  # they can be switched on for a posting that asks, usually a new-grad one.
  gpa: '3.8 / 4.0'
  coursework: [Distributed Systems, Compilers]
  notes: Thesis on incremental type checking
  priority: 2
  links:
    - label: Thesis
      url: example.com/thesis

---

# Certifications
  # status is one of: earned, in_progress, expired
  # Only earned certifications are ever printed. An in-progress course is not a
  # certification, and printing one as though it were is the fastest way to lose
  # a room. Keep it here so you can mention it out loud.
- name: Certification Name
  issuer: Who issued it
  date: 2023-04
  expires: 2026-04
  status: earned
  url: credly.com/badges/you
- name: A Course You Are Halfway Through
  issuer: Provider
  status: in_progress

---

# Publications
  # type is one of: talk, article, paper, patent, book, podcast
  # Leave the section empty if you have none. An empty section is not a failure.
- type: talk
  title: What you spoke about
  venue: Conference or meetup name
  date: 2025-09
  url: youtube.com/watch?v=example

---

# Awards
- name: Award Name
  issuer: Who gave it
  date: 2024-11
  note: One line on what it was for, if it is not obvious from the name

---

# Languages
  # level is one of: native, fluent, professional, conversational, basic
  # Be honest here specifically. This is the field most likely to be tested
  # without warning, in the first two minutes of a call.
- name: English
  level: native
- name: French
  level: basic
  note: Can read, would struggle in a technical discussion

---

# Availability
  # Never printed. This is what lets the tool score a posting before you spend
  # an hour tailoring for it, and tell you plainly when something is a bad fit.
work_modes: [hybrid, on-site, remote]
locations: [Montreal QC, anywhere in Canada]
earliest_start: 2026-09
notice_period: two weeks
employment_types: [full-time, contract]
compensation:
  currency: CAD
  minimum: 80000
  target: 100000
  # note is where you say what would move the number.
  note: Flexible downward for a strong team or a stack I want to be in.
travel_ok: occasional
  # deal_breakers: things that make a posting a no regardless of everything else.
deal_breakers:
  - Roles requiring relocation outside Canada
  - Unpaid trial projects
  # will_not_work_on: subject matter you decline. Separate from deal_breakers
  # because the tool words the rejection differently.
will_not_work_on: []

---

# Gaps
  # Never printed. An explicit register of what you cannot do, so the selector
  # reports a gap instead of stretching a bullet to cover it.
  # status is one of: none, learning, personal-only, rusty
  # This section is the reason the tool can be trusted. Fill it in properly.
- skill: Kubernetes
  status: none
  bridge: None planned
  blocks: Platform and SRE roles
- skill: Angular
  status: learning
  bridge: Building a real tool in it; Vue experience is the honest transferable part
  blocks: Roles requiring Angular on day one
- skill: React Native
  status: rusty
  bridge: Shipped two apps, but nothing written in the last four months
  blocks: Nothing, but review the codebases before a mobile interview

---

# Rules
  # Never printed. Generation constraints that apply to every CV built from
  # this file. Everything here is optional; the defaults are sensible.
banned_words:
  # Words the generator must never produce, whatever the posting asks for.
  - architected
  - spearheaded
  - responsible for
  - passionate
banned_chars:
  # Written as codepoints so this file itself contains none of them.
  - U+2014
  - U+2013
preferred_phrasing:
  # from: to. Quote any value containing a colon.
  architected: built from scratch
  utilised: used
max_bullets_per_project: 3
max_projects: 5
page_limit: 1