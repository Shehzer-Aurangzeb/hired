// Mirrors backend/app/models.py. Every route behind these is live: nothing in
// the app is mocked any more.

// ---------- profile (GET /api/profile, live) ----------

/** Bookkeeping. schema_version is what lets an old file be migrated later. */
export interface Meta {
  schema_version: number;
  updated: string;
}

/** Anything in a CV header that is not one of the named fields below. */
export interface Link {
  label: string;
  url: string;
}

export interface Identity {
  name: string;
  location: string;
  email: string;
  phone: string;
  linkedin: string;
  github: string;
  portfolio: string;
  links: Link[];
  relocation: string;
  authorization: string;
}

export interface Title {
  id: string;
  text: string;
  /** Not printed. Tells the selector which framing a posting calls for. */
  use_when: string;
}

export interface Summary {
  id: string;
  text: string;
  max_chars: number;
}

export interface SkillLine {
  line: string;
  items: string[];
  never_standalone: string[];
  gated: string[];
}

/**
 * Never printed. How "5+ years of React" gets answered from the file rather
 * than guessed, and how a gated skill gets refused when the project that
 * evidences it is not on the page.
 */
export interface SkillEvidence {
  name: string;
  years: number | null;
  last_used: string;
  /** familiar | working | advanced | expert */
  level: string;
  /** professional | personal | academic */
  context: string;
  /** Project ids, from either list, that prove it. */
  evidence: string[];
  gated: boolean;
}

export interface ClaimBoundary {
  can_claim: string[];
  cannot_claim: string[];
  required_qualifiers: string[];
}

/** Where a number in a bullet came from. Absent is itself an answer. */
export interface Metric {
  value: string;
  /** measured | estimated | reported | none */
  source: string;
  method: string;
}

export interface Bullet {
  id: string;
  text: string;
  priority: number;
  tags: string[];
  status: 'active' | 'blocked';
  /** An alternative wording for when the page is one line too long. */
  short: string;
  metric: Metric | null;
  blocked_reason: string;
}

export interface Project {
  id: string;
  name: string;
  label: string;
  stack: string[];
  /** Your actual scope, in the words you would use under questioning. */
  my_role: string;
  /** live | shipped | internal | pilot | sunset | abandoned */
  status: string;
  domain: string;
  start: string;
  end: string;
  /** Not printed. The answer when an interviewer asks why this exists. */
  why_built: string;
  priority: number;
  tags: string[];
  disclosure: string;
  /** True things you cannot evidence today. Each should have a blocked bullet. */
  unverified: string[];
  /** Repo, live demo, case study, app store listing. */
  links: Link[];
  claim_boundary: ClaimBoundary;
  bullets: Bullet[];
}

/** A promotion inside the same employer. Newest first, current one excluded. */
export interface PreviousRole {
  role: string;
  start: string;
  end: string;
}

export interface Experience {
  name: string;
  role: string;
  start: string;
  end: string;
  location: string;
  /** full-time | part-time | contract | freelance | internship | volunteer */
  employment_type: string;
  context: string;
  /** What you may say about this employer in public. Not printed. */
  disclosure: string;
  previous_roles: PreviousRole[];
  priority: number;
  projects: Project[];
}

export interface Education {
  school: string;
  degree: string;
  field: string;
  location: string;
  start: string;
  end: string;
  /** Off the page by default, switched on for a posting that asks. */
  gpa: string;
  coursework: string[];
  notes: string;
  priority: number;
  links: Link[];
}

export interface Certification {
  name: string;
  issuer: string;
  date: string;
  /** earned | in_progress | expired. Only earned is ever printed. */
  status: string;
  expires: string;
  url: string;
}

export interface Publication {
  /** talk | article | paper | patent | book | podcast */
  type: string;
  title: string;
  venue: string;
  date: string;
  url: string;
}

export interface Award {
  name: string;
  issuer: string;
  date: string;
  note: string;
}

export interface Language {
  name: string;
  /** native | fluent | professional | conversational | basic */
  level: string;
  note: string;
}

/**
 * Never printed. The register of what you cannot do, so the selector reports a
 * gap instead of stretching a bullet to cover it.
 */
export interface Gap {
  skill: string;
  /** none | learning | personal-only | rusty */
  status: string;
  bridge: string;
  blocks: string;
}

/** Never printed. What lets a posting be scored before an hour goes into it. */
export interface Availability {
  work_modes: string[];
  locations: string[];
  earliest_start: string;
  notice_period: string;
  employment_types: string[];
  /** Free-shaped: currency, minimum, target, note, whatever else. */
  compensation: Record<string, unknown>;
  travel_ok: string;
  deal_breakers: string[];
  will_not_work_on: string[];
}

/** Never printed. Generation constraints that apply to every CV from this file. */
export interface Rules {
  banned_words: string[];
  banned_chars: string[];
  preferred_phrasing: Record<string, string>;
  max_bullets_per_project: number;
  max_projects: number;
  page_limit: number;
}

export interface Profile {
  meta: Meta;
  identity: Identity;
  titles: Title[];
  summaries: Summary[];
  skills: SkillLine[];
  skill_evidence: SkillEvidence[];
  experience: Experience[];
  /** Work with no employer: personal builds, open source, academic. */
  projects: Project[];
  education: Education[];
  certifications: Certification[];
  publications: Publication[];
  awards: Award[];
  languages: Language[];
  availability: Availability;
  gaps: Gap[];
  rules: Rules;
}

// ---------- profile source (the raw markdown, live) ----------

export interface ProfileSource {
  text: string;
  exists: boolean;
  updated_at: string | null;
  /** Which saved version this text is. Null before anything has been saved. */
  version: number | null;
}

/** One entry in the history list. The text is deliberately absent: with it, the
 *  list would be a megabyte. */
export interface ProfileVersion {
  version: number;
  updated_at: string;
  chars: number;
  current: boolean;
}

export interface DiffLine {
  /** "+" added, "-" removed, " " context, "@" a jump between hunks. */
  op: string;
  text: string;
}

/** Already in display order. Render it straight; there is no line maths to do. */
export interface ProfileDiff {
  from_version: number;
  to_version: number;
  added: number;
  removed: number;
  lines: DiffLine[];
}

/** GET /api/profile/template. Both strings are backend config, not code. */
export interface ProfileTemplate {
  text: string;
  claude_prompt: string;
}

export interface ProfileIssue {
  /** 1-indexed, or null when the problem is not tied to a line. */
  line: number | null;
  message: string;
}

export interface ProfileSummary {
  /** Projects under an employer. projects_total counts the standalone ones too. */
  projects: number;
  projects_total: number;
  bullets: number;
  blocked: number;
  missing_boundaries: number;
  skills_evidenced: number;
  gaps: number;
  unverified: number;
}

export interface ValidationResult {
  ok: boolean;
  errors: ProfileIssue[];
  warnings: ProfileIssue[];
  summary: ProfileSummary | null;
}

// ---------- the fit check and the selector ----------

export interface RequiredSkill {
  name: string;
  importance: 1 | 2 | 3;
}

export interface ParsedJd {
  company: string;
  role: string;
  seniority: string;
  location: string;
  work_mode: string;
  required_skills: RequiredSkill[];
  preferred_skills: RequiredSkill[];
  keywords: string[];
  french_required: boolean;
  years_required: number | null;
}

export interface Fit {
  score: number;
  reasoning: string;
  gaps: string[];
}

export interface SelectedBullet {
  id: string;
  text: string;
  source_id: string;
  rephrased: boolean;
}

export interface CvSection {
  project_id: string;
  /** Not in the plan's sketch. The UI needs a human label for the group header. */
  project_name: string;
  label: string;
  stack: string[];
  bullets: SelectedBullet[];
}

/** One posting requirement and the bullets on the page that back it. */
export interface SkillCoverage {
  skill: string;
  bullet_ids: string[];
}

export interface GeneratedCv {
  title: string;
  summary: string;
  skills_lines: { line: string; items: string[] }[];
  sections: CvSection[];
  coverage: SkillCoverage[];
}

/** block stops export. warn is a claim-boundary gap that needs a human decision. */
export interface Flag {
  type: 'block' | 'warn';
  message: string;
}

/** POST /api/fit. Runs before anything is saved and writes nothing. */
/** A row already on file for the same employer. */
export interface PriorApplication {
  id: number;
  role: string;
  status: ApplicationStatus;
  created_at: string;
  applied_at: string | null;
}

export interface FitResponse {
  parsed_jd: ParsedJd;
  fit: Fit;
  seen: PriorApplication[];
}

/** POST /api/generate. The posting was already read by the fit check. */
export interface GenerateRequest {
  jd_text: string;
  parsed_jd: ParsedJd;
  title_variant?: string;
}

export interface GenerateResponse {
  cv: GeneratedCv;
  flags: Flag[];
}

/** POST /api/export. Attaches a PDF to a row that already exists. */
export interface ExportResponse {
  id: number;
  filename: string;
  page_count: number;
}

// ---------- applications ----------

/**
 * Where you are with an employer. Whether a CV exists is a separate fact
 * (has_pdf), which is why there is no "generated" stage.
 */
export const APPLICATION_STATUSES = [
  'saved',
  'skipped',
  'applied',
  'replied',
  'interview',
  'rejected',
  'offer',
] as const;

export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

/**
 * A bullet as it appeared on the exported PDF. Stored on the record rather than
 * joined against the live profile at read time, because master.md keeps
 * changing and this view has to show what the employer actually read.
 */
export interface SentBullet {
  id: string;
  text: string;
  project_name: string;
}

/**
 * A job posting you decided to keep. Not "a CV you sent": the records worth the
 * most are often the ones you did not apply to, kept for the gaps they exposed,
 * so everything CV-shaped is nullable.
 */
export interface Application {
  id: number;
  company: string;
  role: string;
  source: string | null;
  url: string | null;
  jd_text: string;
  jd_parsed: ParsedJd;
  fit_score: number;
  fit_reasoning: string;
  gaps: string[];
  title_variant: string | null;
  summary_text: string | null;
  selected_bullet_ids: string[];
  selected_bullets: SentBullet[];
  coverage: SkillCoverage[];
  /** The bytes come from /api/applications/{id}/pdf, never from this payload. */
  has_pdf: boolean;
  filename: string | null;
  status: ApplicationStatus;
  applied_at: string | null;
  created_at: string;
  notes: string | null;
}
