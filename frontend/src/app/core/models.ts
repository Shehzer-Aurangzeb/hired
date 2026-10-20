// ---------- profile ----------

export interface Meta {
  schema_version: number;
  updated: string;
}

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
  /** Not printed. Tells the selector when to use this framing. */
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

/** Not printed. Backs skill claims with projects. */
export interface SkillEvidence {
  name: string;
  years: number | null;
  last_used: string;
  /** familiar | working | advanced | expert */
  level: string;
  /** professional | personal | academic */
  context: string;
  /** Project ids that prove it. */
  evidence: string[];
  gated: boolean;
}

export interface ClaimBoundary {
  can_claim: string[];
  cannot_claim: string[];
  required_qualifiers: string[];
}

/** Where a number in a bullet came from. */
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
  /** Shorter wording for when the page runs long. */
  short: string;
  metric: Metric | null;
  blocked_reason: string;
}

export interface Project {
  id: string;
  name: string;
  label: string;
  stack: string[];
  my_role: string;
  /** live | shipped | internal | pilot | sunset | abandoned */
  status: string;
  domain: string;
  start: string;
  end: string;
  /** Not printed. */
  why_built: string;
  priority: number;
  tags: string[];
  disclosure: string;
  /** True but not yet provable. */
  unverified: string[];
  links: Link[];
  claim_boundary: ClaimBoundary;
  bullets: Bullet[];
}

/** Earlier roles at the same employer. Newest first, current excluded. */
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
  /** Not printed. What you may say about this employer publicly. */
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
  /** Hidden unless a posting asks for it. */
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

/** Not printed. Known gaps, so the selector reports them instead of stretching. */
export interface Gap {
  skill: string;
  /** none | learning | personal-only | rusty */
  status: string;
  bridge: string;
  blocks: string;
}

/** Not printed. Used when scoring a posting. */
export interface Availability {
  work_modes: string[];
  locations: string[];
  earliest_start: string;
  notice_period: string;
  employment_types: string[];
  /** Free-form: currency, minimum, target, etc. */
  compensation: Record<string, unknown>;
  travel_ok: string;
  deal_breakers: string[];
  will_not_work_on: string[];
}

/** Not printed. Constraints applied to every generated CV. */
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
  /** Projects with no employer. */
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

// ---------- profile source (raw markdown) ----------

export interface ProfileSource {
  text: string;
  exists: boolean;
  updated_at: string | null;
  /** Null before the first save. */
  version: number | null;
}

/** History entry, without the text to keep the list small. */
export interface ProfileVersion {
  version: number;
  updated_at: string;
  chars: number;
  current: boolean;
}

/** Ask chat turn, replayed each request since the model is stateless. */
export interface AskTurn {
  role: 'you' | 'model';
  text: string;
}

/** A proposed edit, sent back each turn. */
export interface AskChange {
  op: string;
  target: string;
  [field: string]: unknown;
}

/** Nothing is saved until `text` goes through save(). */
export interface AskReply {
  reply: string;
  questions: string[];
  changes: AskChange[];
  /** The proposed profile, or null if nothing could be applied. */
  text: string | null;
  diff: DiffLine[];
  added: number;
  removed: number;
  /** Changes that were rejected, with reasons. */
  refused: string[];
}

export interface DiffLine {
  /** "+" added, "-" removed, " " context, "@" a jump between hunks. */
  op: string;
  text: string;
}

/** Already in display order. */
export interface ProfileDiff {
  from_version: number;
  to_version: number;
  added: number;
  removed: number;
  lines: DiffLine[];
}

/** GET /api/profile/template */
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
  /** Projects under an employer; projects_total includes standalone ones. */
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
  project_name: string;
  label: string;
  stack: string[];
  bullets: SelectedBullet[];
}

/** One posting requirement and the bullets on the page that back it. */
export interface SkillCoverage {
  /** What backs a requirement no bullet can: a degree, or nothing a CV shows. */
  backed_by?: string;
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

/** `block` stops export; `warn` needs a human decision. */
export interface Flag {
  type: 'block' | 'warn';
  message: string;
}

/** An existing application to the same employer. */
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
  /** Which model answered. Empty in demo mode and on older rows. */
  model: string;
  /** Set when the first answer was unusable and the call was repeated. */
  notice?: string;
}

/** POST /api/generate */
export interface GenerateRequest {
  /** Which model to answer with. Empty means the backend's configured routing. */
  model?: string;
  jd_text: string;
  parsed_jd: ParsedJd;
  title_variant?: string;
}

export interface GenerateResponse {
  cv: GeneratedCv;
  flags: Flag[];
  /** Which model answered, so a fallback to the local one is visible. */
  model: string;
  /** Set when the first answer was unusable and the call was repeated. */
  notice?: string;
}

/** POST /api/export. Attaches a PDF to an existing row. */
export interface ExportResponse {
  id: number;
  filename: string;
  page_count: number;
}

// ---------- applications ----------

/** Whether a CV exists is tracked separately (has_pdf). */
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

/** A bullet exactly as sent, stored since the profile keeps changing. */
export interface SentBullet {
  id: string;
  text: string;
  project_name: string;
}

/** A saved posting. CV fields are nullable since you may not have applied. */
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
  /** Which model chose the bullets on the saved PDF. Empty on older rows. */
  model: string;
  /** Which model read the posting and scored it. Empty on older rows. */
  fit_model: string;
  /** Emails and form answers written for this posting, newest last. */
  artifacts: Artifact[];
  /** The PDF itself is at /api/applications/{id}/pdf. */
  has_pdf: boolean;
  filename: string | null;
  status: ApplicationStatus;
  applied_at: string | null;
  created_at: string;
  notes: string | null;
}

/** An email or a form answer, written from the application and kept on it. */
export interface Artifact {
  kind: 'email' | 'answer';
  /** The question, for an answer. Empty for an email. */
  question: string;
  /** The subject line, for an email. Empty for an answer. */
  subject: string;
  body: string;
  model: string;
  created_at: string;
  /** Banned phrases found in the text. Only on a freshly written one: it is a
   *  verdict on today's rules, not a fact about the artifact. */
  flags?: Flag[];
}
