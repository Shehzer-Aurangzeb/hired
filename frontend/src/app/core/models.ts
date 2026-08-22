// Mirrors backend/app/models.py plus the API contract in hired_BUILD_PLAN.md.
// Where the backend does not exist yet, these interfaces ARE the spec it has to
// satisfy. core/mock-data.ts is the worked example.

// ---------- profile (GET /api/profile, live) ----------

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

export interface ClaimBoundary {
  can_claim: string[];
  cannot_claim: string[];
  required_qualifiers: string[];
}

export interface Bullet {
  id: string;
  text: string;
  priority: number;
  tags: string[];
  status: 'active' | 'blocked';
}

export interface Project {
  id: string;
  name: string;
  label: string;
  stack: string[];
  priority: number;
  tags: string[];
  disclosure: string;
  /** Repo, live demo, case study, app store listing. */
  links: Link[];
  claim_boundary: ClaimBoundary;
  bullets: Bullet[];
}

export interface Experience {
  name: string;
  role: string;
  start: string;
  end: string;
  location: string;
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
  notes: string;
  links: Link[];
}

export interface Certification {
  name: string;
  issuer: string;
  date: string;
  url: string;
}

export interface Language {
  name: string;
  level: string;
}

export interface Profile {
  identity: Identity;
  titles: Title[];
  summaries: Summary[];
  skills: SkillLine[];
  experience: Experience[];
  education: Education[];
  certifications: Certification[];
  languages: Language[];
}

// ---------- profile source (the raw markdown, not built yet) ----------

export interface ProfileSource {
  text: string;
  exists: boolean;
  updated_at: string | null;
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
  projects: number;
  bullets: number;
  blocked: number;
  missing_boundaries: number;
}

export interface ValidationResult {
  ok: boolean;
  errors: ProfileIssue[];
  warnings: ProfileIssue[];
  summary: ProfileSummary | null;
}

// ---------- generate (POST /api/generate, not built yet) ----------

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

export interface GeneratedCv {
  title: string;
  summary: string;
  skills_lines: { line: string; items: string[] }[];
  sections: CvSection[];
}

/** block stops export. warn is a claim-boundary gap that needs a human decision. */
export interface Flag {
  type: 'block' | 'warn';
  message: string;
}

export interface GenerateRequest {
  jd_text: string;
  company?: string;
  role?: string;
  title_variant?: string;
}

export interface GenerateResponse {
  parsed_jd: ParsedJd;
  fit: Fit;
  cv: GeneratedCv;
  flags: Flag[];
}

export interface ExportResponse {
  filename: string;
  page_count: number;
}

// ---------- applications (not built yet) ----------

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
  jd_text: string;
  jd_parsed: ParsedJd;
  fit_score: number;
  fit_reasoning: string;
  gaps: string[];
  title_variant: string | null;
  summary_text: string | null;
  selected_bullet_ids: string[];
  selected_bullets: SentBullet[];
  /** The bytes come from /api/applications/{id}/pdf, never from this payload. */
  has_pdf: boolean;
  filename: string | null;
  status: ApplicationStatus;
  applied_at: string | null;
  created_at: string;
  notes: string | null;
}
