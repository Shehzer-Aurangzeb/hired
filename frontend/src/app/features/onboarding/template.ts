/**
 * Starter profile handed out by "Start from a template".
 *
 * ponytail: lives here while `GET /api/profile/template` is mocked. The backend
 * owns it once that route is real, and this file gets deleted.
 */
export const PROFILE_TEMPLATE = `# Identity
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
`;
