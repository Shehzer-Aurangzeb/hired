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
      return 'bg-royal-soft text-royal';
    case 'interview':
      return 'bg-accent-soft text-accent';
    case 'replied':
      return 'bg-warn-soft text-warn';
    case 'rejected':
      return 'bg-danger-soft text-danger';
    // Most of the list. Grey here meant the status seen most often was the one
    // carrying no signal.
    case 'applied':
      return 'bg-info-soft text-info';
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

/**
 * The funnel: how many reached each stage, not how many sit there now.
 *
 * Status is a single current value, so counting rows at "replied" misses
 * everyone who already moved to interview. Each stage below therefore counts
 * itself plus everything past it, which is what makes a conversion rate mean
 * anything.
 *
 * A rejection is a human response, so it counts as having heard back. The
 * split between a yes and a no belongs under the funnel, not inside it.
 */
export interface Stage {
  label: string;
  count: number;
  /** Share of the stage above, or null for the first one. */
  rate: number | null;
  segment: Segment | null;
  /** Deepens along the funnel. One hue, because the stages are ordered: a
   *  categorical palette would say they are five unrelated things. */
  tone: string;
}

// Each stage in the hue its own rows wear, so a chip in the funnel and a chip
// in the table mean the same thing. A single ramp looked tidy and taught
// nothing.
const TONES = [
  'bg-surface text-fg-muted',
  'bg-info-soft text-info',
  'bg-warn-soft text-warn',
  'bg-accent-soft text-accent',
  'bg-royal-soft text-royal',
];

const REACHED: Record<string, ApplicationStatus[]> = {
  Saved: ['saved', 'skipped', 'applied', 'replied', 'interview', 'rejected', 'offer'],
  Sent: ['applied', 'replied', 'interview', 'rejected', 'offer'],
  'Heard back': ['replied', 'interview', 'rejected', 'offer'],
  Interview: ['interview', 'offer'],
  Offer: ['offer'],
};

export function funnel(applications: Application[]): Stage[] {
  const segments: (Segment | null)[] = [null, null, null, 'interview', 'offer'];
  let previous = 0;
  return Object.entries(REACHED).map(([label, statuses], index) => {
    const count = applications.filter((a) => statuses.includes(a.status)).length;
    const rate = index === 0 || !previous ? null : Math.round((count / previous) * 100);
    previous = count;
    // An empty stage stays grey: colouring a zero implies something is there.
    const tone = count ? TONES[index] : 'bg-surface/60 text-fg-subtle';
    return { label, count, rate, segment: segments[index], tone };
  });
}

/**
 * Consecutive days, counting back from today, that met the target.
 *
 * Today only breaks the streak once it is over, so a day that has not finished
 * yet is skipped rather than counted as a failure. Nobody wants to be told at
 * 9am that they are on zero.
 */
export function streak(applications: Application[], target: number): number {
  const byDay = new Map<string, number>();
  for (const a of applications) {
    if (!a.applied_at) continue;
    const key = new Date(a.applied_at).toLocaleDateString('en-CA');
    byDay.set(key, (byDay.get(key) ?? 0) + 1);
  }

  let days = 0;
  const cursor = new Date();
  if ((byDay.get(cursor.toLocaleDateString('en-CA')) ?? 0) < target) {
    cursor.setDate(cursor.getDate() - 1);
  }
  while ((byDay.get(cursor.toLocaleDateString('en-CA')) ?? 0) >= target) {
    days += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return days;
}
