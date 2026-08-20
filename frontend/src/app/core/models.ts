// Mirrors backend/app/models.py plus the API contract in hired_BUILD_PLAN.md.
// Where the backend does not exist yet, these interfaces ARE the spec it has to
// satisfy. core/mock-data.ts is the worked example.

// ---------- profile (GET /api/profile, live) ----------

export interface Identity {
  name: string;
  location: string;
  email: string;
  phone: string;
  linkedin: string;
  github: string;
  portfolio: string;
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

export interface Profile {
  identity: Identity;
  titles: Title[];
  summaries: Summary[];
  skills: SkillLine[];
  experience: Experience[];
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
  pdf_path: string;
  filename: string;
  page_count: number;
}

// ---------- applications (not built yet) ----------

export const APPLICATION_STATUSES = [
  'generated',
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
  title_variant: string;
  selected_bullet_ids: string[];
  selected_bullets: SentBullet[];
  summary_text: string;
  pdf_path: string;
  filename: string;
  status: ApplicationStatus;
  applied_at: string | null;
  created_at: string;
  notes: string | null;
}
