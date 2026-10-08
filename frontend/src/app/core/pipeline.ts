import { Application, ApplicationStatus } from './models';
import { daysSince } from './dates';

/** Days in Applied with no reply before it counts as ghosted. */
export const FOLLOW_UP_DAYS = 10;

/** `waiting` and `ghosted` are both status 'applied', split by days since sent. */
export type Segment =
  | 'saved'
  | 'waiting'
  | 'replied'
  | 'interview'
  | 'offer'
  | 'ghosted'
  | 'rejected'
  | 'skipped';

// Colours are checked for contrast and colour-blindness in this order, so recheck if reordered.
// The two never-sent stages share a grey and differ only by hatch angle.
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

/** Statuses that mean it was sent. Keep in sync with SENT in backend/app/tables.py. */
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

/** Bands match the scoring prompt: 7-10 good fit, 4-6 partial, 1-3 different field. */
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
