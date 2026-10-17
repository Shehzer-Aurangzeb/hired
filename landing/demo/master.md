# Identity
name: Maya Okafor
location: Toronto, ON
email: maya@example.com
phone: +1 416 555 0142
linkedin: linkedin.com/in/maya-okafor
github: github.com/mayaokafor
portfolio: mayaokafor.dev
authorization: Canadian citizen, no sponsorship required

# Titles
- id: frontend
  text: 'Front-End Engineer | React · TypeScript · Design Systems'
  use_when: Posting is front-end only. Default when nothing else fits.
- id: fullstack
  text: 'Full-Stack Engineer | React · Node.js · PostgreSQL'
  use_when: Posting asks for API design, backend ownership or database work.

# Summaries
- id: frontend
  max_chars: 520
  text: >
    Front-end engineer with five years of React and TypeScript, most of it on
    data-heavy products where the interface has to stay fast as the data grows.
    I build design systems that other teams adopt, and I care about the details
    that make a dense screen easy to read.
- id: fullstack
  max_chars: 520
  text: >
    Full-stack engineer with five years of TypeScript, comfortable owning a
    feature from the PostgreSQL schema to the last pixel. Most recently built
    the reporting stack for a fintech team of twelve.

# Skills
- line: Frontend
  items: [React, TypeScript, Next.js, TanStack Query, Tailwind CSS, Storybook, Accessibility, Table virtualisation]
- line: Backend
  items: [Node.js, PostgreSQL, GraphQL, REST]
- line: Tooling
  items: [Vitest, Playwright, GitHub Actions, Docker, AWS]
  gated: [AWS]

# Skill Evidence
- name: React
  years: 5
  last_used: 2026-09
  level: expert
  context: professional
  evidence: [ledgerline-app, northwind-design-system]
- name: TypeScript
  years: 5
  last_used: 2026-09
  level: advanced
  context: professional
  evidence: [ledgerline-app, ledgerline-reports]
- name: PostgreSQL
  years: 2
  last_used: 2026-06
  level: working
  context: professional
  evidence: [ledgerline-reports]
- name: AWS
  years: 0.5
  last_used: 2025-11
  level: familiar
  context: personal
  evidence: [tidepool]
  gated: true

# Experience
## Ledgerline
role: Senior Front-End Engineer
location: Toronto, ON
start: 2023-03
end: present
priority: 1

### Ledgerline App
label: Accounting platform for small businesses
stack: [React, TypeScript, TanStack Query]
priority: 1
tags: [frontend, react, performance]

claim_boundary:
  can_claim:
    - Led the front-end rebuild, one of three engineers on it
    - Owned the table virtualisation work end to end
  cannot_claim:
    - Led the team. There was an engineering manager.
    - Any revenue or conversion number. Never measured by us.
  required_qualifiers:
    - 'cutting p75 load time'

bullets:
  - id: ledgerline-rebuild
    priority: 1
    tags: [frontend, react, ownership]
    text: Rebuilt the invoicing front-end in React and TypeScript with two other engineers, retiring a seven-year-old jQuery codebase.
  - id: ledgerline-virtual
    priority: 1
    tags: [performance, react]
    text: Virtualised the transactions table so 50,000-row ledgers scroll smoothly, cutting p75 load time by 40%.
    metric:
      value: '40%'
      source: measured
      method: p75 load time from Datadog RUM, four weeks before and after
  - id: ledgerline-cache
    priority: 2
    tags: [performance, caching, data]
    text: Moved data fetching to TanStack Query with optimistic updates, removing a hand-rolled Redux cache.
  - id: ledgerline-a11y
    priority: 2
    tags: [accessibility, frontend]
    text: Brought the invoice editor to WCAG 2.2 AA, fixing 63 audit findings across keyboard and screen-reader paths.
    metric:
      value: '63'
      source: measured
      method: Count of findings in the external audit report
  - id: ledgerline-ai
    priority: 3
    status: blocked
    blocked_reason: Prototype only. Never shipped to customers.
    tags: [ai]
    text: Built AI-assisted invoice categorisation.

### Ledgerline Reports
label: Reporting service
stack: [Node.js, PostgreSQL, GraphQL]
priority: 2
tags: [backend, fullstack]

claim_boundary:
  cannot_claim:
    - Designed the warehouse. Consumed the existing schema.

bullets:
  - id: reports-graphql
    priority: 2
    tags: [backend, graphql, api]
    text: Built the GraphQL reporting API in Node.js over PostgreSQL, serving twelve report types.
  - id: reports-export
    priority: 3
    tags: [backend, performance]
    text: Streamed CSV exports instead of buffering them, ending the out-of-memory crashes on large accounts.
  - id: reports-schedules
    priority: 2
    tags: [backend, fullstack]
    text: Added scheduled report delivery by email, now the most-used feature among accountants on the platform.

## Northwind Studio
role: Front-End Developer
location: Remote
start: 2021-06
end: 2023-02
priority: 2

### Northwind Design System
label: Component library for agency clients
stack: [React, Storybook, Tailwind CSS]
priority: 2
tags: [frontend, design-systems]

claim_boundary:
  cannot_claim:
    - Created the visual design. Designers owned it; I built it.

bullets:
  - id: northwind-ds
    priority: 1
    tags: [design-systems, frontend, react]
    text: Built a 40-component React library in Storybook, adopted by six client projects.
    metric:
      value: '6'
      source: reported
      method: Client projects importing the package, per the agency's repo list
  - id: northwind-tests
    priority: 2
    tags: [testing, frontend]
    text: Added visual regression tests with Playwright, catching layout breaks before release.
  - id: northwind-tokens
    priority: 2
    tags: [design-systems, frontend]
    text: Introduced design tokens shared between Figma and code, so a brand change became a single pull request.
  - id: northwind-docs
    priority: 3
    tags: [design-systems, documentation]
    text: Wrote usage guidelines for every component, cutting design-review back-and-forth on client projects.

# Projects
### Tidepool
label: Open-source tide chart app
stack: [Next.js, AWS Lambda]
priority: 3
tags: [personal, nextjs]

claim_boundary:
  cannot_claim:
    - Production AWS experience. One Lambda, personal scale.

bullets:
  - id: tidepool-app
    priority: 3
    tags: [nextjs, personal]
    text: Built a Next.js tide chart app on AWS Lambda, used by about 300 kayakers a month.
    metric:
      value: '~300'
      source: measured
      method: Monthly unique visitors, Plausible
  - id: tidepool-offline
    priority: 3
    tags: [nextjs, pwa]
    text: Made the charts work offline as a PWA, since most users check them on the water with no signal.

# Education
- school: University of Waterloo
  degree: BMath
  field: Computer Science
  location: Waterloo, ON
  start: 2016-09
  end: 2021-04

# Languages
- name: English
  level: native
- name: French
  level: conversational

# Gaps
- skill: React Native
  status: none
  bridge: None planned
  blocks: Mobile roles
- skill: Kubernetes
  status: none
  bridge: None planned
  blocks: Platform roles

# Rules
banned_words: [spearheaded, leveraged, synergy]
max_bullets_per_project: 4
max_projects: 4
