# Identity
name: Test Person
location: Montreal, QC
relocation: Open to relocation
email: test@example.com
phone: +1 514 000 0000
linkedin: linkedin.com/in/test
portfolio: example.com
github: github.com/test
links:
  - label: Dribbble
    url: dribbble.com/test
  - Stack Overflow: stackoverflow.com/users/1/test
  - https://www.medium.com/@test
authorization: Authorized to work in Canada, no sponsorship required

# Titles
- id: fullstack
  text: Full-Stack Engineer | React · Next.js · TypeScript · Node.js
- id: frontend
  text: Front-End Engineer | React · TypeScript · Next.js · Design Systems

# Summaries
- id: fullstack
  max_chars: 520
  text: >
    Full-stack engineer with 3.5+ years in TypeScript across the front-end
    and back-end.

# Skills
- line: Frontend
  items: [React, Next.js, TypeScript, Tailwind, TanStack Query]
- line: Infra
  items: [Docker, GitHub Actions, Vercel, AWS]
  gated: [AWS]                 # only when the evidence project is on the page

# Experience
## Devnito
role: Frontend & Mobile Engineer
location: Remote
start: 2024-11
end: present
priority: 1

### Dedicate
label: VC-backed asset management platform
stack: [Next.js, React, TypeScript]
priority: 1
tags: [frontend, react, nextjs]
links:
  - Live: dedicate.example.com
  - Case study: example.com/case/dedicate

claim_boundary:
  can_claim:
    - Built the front-end from scratch, front-end lead on a team of ~10
    - Consumed a multi-IDP token chain feeding Skyflow
  cannot_claim:
    - Built Skyflow, or built the vault. Consumed only.
    - Measured performance numbers. The ~50% figure is estimated.
  required_qualifiers:
    - '"~50% reduction in repeat API calls" must always carry the word "estimated"'

bullets:
  - id: dedicate-frontend-scratch
    priority: 1
    tags: [frontend, react, ownership]
    text: Built the front-end from scratch in Next.js and TypeScript on a BFF pattern.
  - id: dedicate-caching
    priority: 2
    tags: [performance, caching]
    text: >
      Built the data layer with TanStack Query and tiered caching across 18 query
      patterns, cutting repeat API calls by an estimated 50%.

### Stanley Paden
label: Home services marketplace
stack: [React Native, Expo]
priority: 3
tags: [mobile]

claim_boundary:
  cannot_claim:
    - In-app purchases, until package.json is confirmed

bullets:
  - id: stanley-mobile
    priority: 2
    tags: [mobile, expo]
    text: Shipped the React Native app to both stores with EAS Build and Submit.
  - id: stanley-iap
    priority: 3
    status: blocked
    tags: [mobile, payments]
    text: Integrated in-app purchases.

## Swift Reflex
role: Full-Stack Developer
location: Remote
start: 2022-01
end: 2023-06
priority: 2

### Swift Reflex Platform
label: Logistics platform
stack: [PHP, Laravel]
priority: 3
tags: [backend, php]
disclosure: Unpaid family work, surface as an interview reminder.

bullets:
  - id: swiftreflex-php
    priority: 3
    tags: [backend, php]
    text: Built CRUD modules and reporting views in PHP and Laravel.

# Education
- school: Concordia University
  degree: BEng
  field: Software Engineering
  location: Montreal, QC
  start: 2018-09
  end: 2022-05

# Certifications
- name: AWS Certified Cloud Practitioner
  issuer: Amazon Web Services
  date: 2023-04
  url: credly.com/badges/test

# Languages
- name: English
  level: Native
- name: French
  level: Professional working
