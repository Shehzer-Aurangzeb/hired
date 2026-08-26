import { Application, ApplicationStatus } from './models';
import { daysSince } from './dates';

/** Sitting in Applied this long with no reply means it needs chasing. */
export const FOLLOW_UP_DAYS = 10;

/**
 * Pipeline stages. `waiting` and `ghosted` are both status 'applied'; the split
 * is derived from how long it has been sitting, because "gone quiet" is the
 * state you actually care about and the schema has no column for it.
 */
export type Segment =
  | 'saved'
  | 'waiting'
  | 'replied'
  | 'interview'
  | 'offer'
  | 'ghosted'
  | 'rejected'
  | 'skipped';

/**
 * Validated with the dataviz palette checker against the beige card surface
 * (#faf7f0): lightness band, CVD separation, normal-vision floor and 3:1
 * contrast all pass in this exact left-to-right order. Reordering can break the
 * adjacent-pair checks, so re-run the validator if you change it.
 *
 * ponytail: ghosted is intentionally below the chroma floor. "Nothing happened"
 * should read as absence of colour, and the legend carries the label anyway.
 *
 * The two never-sent stages have no hue at all. They share one neutral and are
 * told apart by hatch angle, which is the texture channel rather than a seventh
 * and eighth colour the CVD checks would have to survive.
 */
export const SEGMENTS: {
  key: Segment;
  label: string;
  color: string;
  /** Hatch angle in degrees. Absent means a solid fill. */
  hatch?: number;
}[] = [
  { key: 'saved', label: 'Not sent', color: '#b9ae95', hatch: 45 },
  { key: 'waiting', label: 'Waiting', color: '#3a6ea8' },
  { key: 'replied', label: 'Replied', color: '#a86a08' },
  { key: 'interview', label: 'Interview', color: '#0a7f66' },
  { key: 'offer', label: 'Offer', color: '#6b4fa8' },
  { key: 'ghosted', label: 'Ghosted', color: '#8b8378' },
  { key: 'rejected', label: 'Rejected', color: '#b23b2c' },
  { key: 'skipped', label: 'Passed on', color: '#b9ae95', hatch: 135 },
];

/**
 * Reaching any of these means it went out, whatever route it took. Mirrors
 * SENT in backend/app/tables.py; both answer "did an employer see this".
 */
export const SENT_STATUSES: ApplicationStatus[] = [
  'applied',
  'replied',
  'interview',
  'rejected',
  'offer',
];

export function isSent(application: Application): boolean {
  return SENT_STATUSES.includes(application.status);
}

/** Whole days the application has been sitting since it was sent. */
export function waitingDays(application: Application): number {
  return Math.floor(daysSince(application.applied_at));
}

export function inSegment(application: Application, segment: Segment): boolean {
  if (segment === 'ghosted') {
    return application.status === 'applied' && waitingDays(application) > FOLLOW_UP_DAYS;
  }
  if (segment === 'waiting') {
    return application.status === 'applied' && waitingDays(application) <= FOLLOW_UP_DAYS;
  }
  return application.status === segment;
}

/** Tailwind classes for a status pill. Shared so the list and detail agree. */
export function statusClass(status: ApplicationStatus): string {
  switch (status) {
    case 'offer':
    case 'interview':
      return 'bg-accent-soft text-accent';
    case 'replied':
      return 'bg-warn-soft text-warn';
    case 'rejected':
      return 'bg-danger-soft text-danger';
    case 'skipped':
      // A deliberate pass is not a failure, so it gets no colour.
      return 'bg-surface text-fg-subtle';
    default:
      return 'bg-surface text-fg-muted';
  }
}

export function scoreTone(score: number): string {
  if (score >= 8) return 'text-accent';
  if (score >= 6) return 'text-warn';
  return 'text-danger';
}

/**
 * The score as a verdict, on the bands the scoring prompt itself defines:
 * 7-10 is a good fit, 4-6 is real overlap with a gap, 1-3 is a different
 * discipline. Derived rather than asked for, because a threshold is not worth
 * a model call and a stored answer would go stale the moment the profile does.
 */
export function verdict(score: number): 'Apply' | 'Consider' | 'Skip' {
  if (score >= 7) return 'Apply';
  if (score >= 4) return 'Consider';
  return 'Skip';
}

export function verdictClass(score: number): string {
  if (score >= 7) return 'border-accent/50 bg-accent-soft text-accent';
  if (score >= 4) return 'border-warn/50 bg-warn-soft text-warn';
  return 'border-danger/50 bg-danger-soft text-danger';
}
