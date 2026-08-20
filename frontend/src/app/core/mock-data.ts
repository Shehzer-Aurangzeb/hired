// Fixtures for the routes that have no backend yet. Written to be the worked
// example the backend must reproduce, so keep the shapes honest.

import { Application, GenerateResponse, ParsedJd } from './models';

const AIR_CANADA_JD: ParsedJd = {
  company: 'Air Canada',
  role: 'Front-End Developer',
  seniority: 'Intermediate',
  location: 'Montreal, QC',
  work_mode: 'Hybrid',
  required_skills: [
    { name: 'React', importance: 3 },
    { name: 'TypeScript', importance: 3 },
    { name: 'Next.js', importance: 2 },
    { name: 'Accessibility', importance: 2 },
    { name: 'Design systems', importance: 2 },
    { name: 'Kubernetes', importance: 1 },
  ],
  preferred_skills: [
    { name: 'GraphQL', importance: 2 },
    { name: 'Testing', importance: 2 },
    { name: 'French', importance: 1 },
  ],
  keywords: [
    'component library',
    'responsive layouts',
    'WCAG 2.1 AA',
    'CI/CD',
    'cross-functional team',
  ],
  french_required: false,
  years_required: 3,
};

export const MOCK_GENERATE: GenerateResponse = {
  parsed_jd: AIR_CANADA_JD,
  fit: {
    score: 8,
    reasoning:
      'Strong overlap on React, TypeScript, Next.js and design system work, with real accessibility evidence on Dedicate. Loses points on infrastructure ownership, which the posting lists as a requirement rather than a nice to have.',
    gaps: ['Kubernetes', 'GraphQL federation', 'Terraform'],
  },
  cv: {
    title: 'Front-End Engineer | React · TypeScript · Next.js · Design Systems',
    summary:
      'Front-end engineer with 3.5+ years in TypeScript, building product surfaces in React and Next.js on a BFF pattern. Owned a component registry, an adaptive layout system and a tiered caching data layer on a VC-backed platform, working with a team of about ten. Comfortable with keyboard navigation and ARIA as a build requirement rather than a retrofit.',
    skills_lines: [
      {
        line: 'Frontend',
        items: ['React', 'Next.js', 'TypeScript', 'JavaScript', 'Tailwind', 'TanStack Query'],
      },
      { line: 'Backend', items: ['Node.js', 'NestJS', 'PostgreSQL', 'REST', 'Auth0'] },
      { line: 'Testing', items: ['Vitest', 'Playwright'] },
      { line: 'Infra', items: ['Docker', 'GitHub Actions', 'Vercel'] },
    ],
    sections: [
      {
        project_id: 'dedicate',
        project_name: 'Dedicate',
        label: 'VC-backed asset management platform',
        stack: ['Next.js', 'React', 'TypeScript', 'TanStack Query', 'Auth0'],
        bullets: [
          {
            id: 'dedicate-frontend-scratch',
            source_id: 'dedicate-frontend-scratch',
            rephrased: false,
            text: 'Built the front-end from scratch in Next.js and TypeScript on a BFF pattern, as front-end lead on a cross-functional team of about ten.',
          },
          {
            id: 'dedicate-design-system',
            source_id: 'dedicate-design-system',
            rephrased: true,
            text: 'Built a component registry from scratch with every variant rendered on screen, plus adaptive layouts driven by a useBreakpoint hook with separate component trees per breakpoint.',
          },
          {
            id: 'dedicate-caching',
            source_id: 'dedicate-caching',
            rephrased: false,
            text: 'Built the data layer with TanStack Query and tiered caching across 18 query patterns, cutting repeat API calls by an estimated 50%.',
          },
        ],
      },
      {
        project_id: 'hospital-management-system',
        project_name: 'Hospital Management System',
        label: 'Clinic scheduling and records platform',
        stack: ['React', 'TypeScript', 'NestJS', 'PostgreSQL'],
        bullets: [
          {
            id: 'hms-scheduling',
            source_id: 'hms-scheduling',
            rephrased: false,
            text: 'Built the scheduling and records interface in React and TypeScript, covering appointment booking, patient history and role-based views.',
          },
          {
            id: 'hms-forms',
            source_id: 'hms-forms',
            rephrased: false,
            text: 'Built the clinical intake forms with full keyboard navigation and ARIA labelling on every interactive element.',
          },
        ],
      },
      {
        project_id: 'runiq',
        project_name: 'RUNIQ',
        label: 'Running and training companion app',
        stack: ['React Native', 'Expo', 'TypeScript'],
        bullets: [
          {
            id: 'runiq-shipping',
            source_id: 'runiq-shipping',
            rephrased: false,
            text: 'Shipped the mobile client to both app stores with EAS Build, Update and Submit, including staged rollout and over-the-air patching.',
          },
        ],
      },
    ],
  },
  flags: [
    {
      type: 'warn',
      message:
        'JD asks for Kubernetes. No bullet covers it and no claim boundary allows it, so nothing was added.',
    },
    {
      type: 'warn',
      message:
        'JD asks for infrastructure ownership. Dedicate cannot_claim lists product and infrastructure ownership, so the bullet was left alone.',
    },
    {
      type: 'warn',
      message: 'French is listed as preferred. Not claimed anywhere in the profile.',
    },
  ],
};

/** Auto-filled when a ?mock= scenario loads, so the state shows without typing. */
export const MOCK_JD_TEXT =
  'Front-End Developer, Montreal. Build responsive customer-facing interfaces in React and ' +
  'TypeScript, contribute to our component library, and work with designers and back-end ' +
  'engineers to ship features. Requirements: 3+ years front-end, strong React and TypeScript, ' +
  'Next.js, WCAG 2.1 AA accessibility, CI/CD pipelines. Nice to have: GraphQL, testing, French.';

/**
 * Variants of the base fixture, so the states the happy path never reaches get
 * rendered at least once. Append ?mock=<name> to the URL.
 *
 * ponytail: derived from MOCK_GENERATE rather than hand-written, so they cannot
 * drift from the real shape. Deleted with the rest of the mocks.
 */
export function mockGenerate(scenario: string): GenerateResponse {
  switch (scenario) {
    case 'weak':
      return {
        ...MOCK_GENERATE,
        fit: {
          score: 3,
          reasoning:
            'Little overlap. The posting is built around a Java and Kubernetes stack, and nothing in the profile touches either. The React work transfers only as general front-end experience.',
          gaps: ['Java', 'Spring', 'Kubernetes', 'Terraform', 'Kafka'],
        },
      };

    case 'blocked':
      return {
        ...MOCK_GENERATE,
        flags: [
          {
            type: 'block',
            message:
              'Bullet stanley-iap has status blocked. In-app purchases are unverified until package.json is confirmed, so it cannot go on a CV.',
          },
          {
            type: 'block',
            message:
              'The rephrased dedicate-caching bullet dropped the word "estimated" from the 50% figure. required_qualifiers says it must always carry it.',
          },
          ...MOCK_GENERATE.flags,
        ],
      };

    case 'overflow': {
      // Three extra copies of every section, ids suffixed so they stay unique.
      // Enough to push the page-fill estimate past 100%.
      const extra = [1, 2, 3].flatMap((n) =>
        MOCK_GENERATE.cv.sections.map((section) => ({
          ...section,
          project_id: `${section.project_id}-${n}`,
          project_name: `${section.project_name} (${n})`,
          bullets: section.bullets.map((b) => ({ ...b, id: `${b.id}-${n}` })),
        })),
      );
      return {
        ...MOCK_GENERATE,
        cv: { ...MOCK_GENERATE.cv, sections: [...MOCK_GENERATE.cv.sections, ...extra] },
      };
    }

    default:
      return MOCK_GENERATE;
  }
}

export const MOCK_APPLICATIONS: Application[] = [
  application(1, 'Air Canada', 'Front-End Developer', 8, 'interview', '2026-08-02', [
    'Kubernetes',
    'GraphQL federation',
  ]),
  application(2, 'Shopify', 'Senior Front-End Developer', 7, 'applied', '2026-08-09', [
    'Ruby',
    'GraphQL federation',
  ]),
  application(3, 'Lightspeed', 'Full-Stack Developer', 8, 'replied', '2026-08-05', ['Go']),
  application(4, 'Coveo', 'Front-End Engineer', 6, 'rejected', '2026-07-21', [
    'Angular',
    'Java',
    'Kubernetes',
  ]),
  application(5, 'Hopper', 'Mobile Engineer, React Native', 9, 'applied', '2026-08-12', ['Swift']),
  application(6, 'Nuvei', 'Front-End Developer', 5, 'generated', '2026-08-15', [
    '.NET',
    'Azure',
    'Kubernetes',
  ]),
];

function application(
  id: number,
  company: string,
  role: string,
  score: number,
  status: Application['status'],
  created: string,
  gaps: string[],
): Application {
  const slug = company.replace(/[^A-Za-z0-9]/g, '');
  const roleSlug = role.replace(/[^A-Za-z0-9]/g, '');
  return {
    id,
    company,
    role,
    source: id % 2 ? 'LinkedIn' : 'Company site',
    jd_text: `${role} at ${company}. Full posting text saved with the record.`,
    jd_parsed: { ...AIR_CANADA_JD, company, role },
    fit_score: score,
    fit_reasoning: MOCK_GENERATE.fit.reasoning,
    gaps,
    title_variant: score >= 8 ? 'frontend' : 'fullstack',
    selected_bullet_ids: MOCK_GENERATE.cv.sections.flatMap((s) => s.bullets.map((b) => b.id)),
    summary_text: MOCK_GENERATE.cv.summary,
    pdf_path: `storage/output/Shehzar_Abbasi_${slug}_${roleSlug}_${created}.pdf`,
    filename: `Shehzar_Abbasi_${slug}_${roleSlug}_${created}.pdf`,
    status,
    applied_at: status === 'generated' ? null : `${created}T09:00:00`,
    created_at: `${created}T08:30:00`,
    notes: status === 'interview' ? 'Recruiter screen done. Technical round on the 21st.' : null,
  };
}
