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
  | 'generated'
  | 'waiting'
  | 'replied'
  | 'interview'
  | 'offer'
  | 'ghosted'
  | 'rejected';

/**
 * Validated with the dataviz palette checker against the beige card surface
 * (#faf7f0): lightness band, CVD separation, normal-vision floor and 3:1
 * contrast all pass in this exact left-to-right order. Reordering can break the
 * adjacent-pair checks, so re-run the validator if you change it.
 *
 * ponytail: ghosted is intentionally below the chroma floor. "Nothing happened"
 * should read as absence of colour, and the legend carries the label anyway.
 * `generated` has no hue at all; it is hatched, so no seventh colour is needed.
 */
export const SEGMENTS: { key: Segment; label: string; color: string; hatched?: boolean }[] = [
  { key: 'generated', label: 'Not sent', color: '#b9ae95', hatched: true },
  { key: 'waiting', label: 'Waiting', color: '#3a6ea8' },
  { key: 'replied', label: 'Replied', color: '#a86a08' },
  { key: 'interview', label: 'Interview', color: '#0a7f66' },
  { key: 'offer', label: 'Offer', color: '#6b4fa8' },
  { key: 'ghosted', label: 'Ghosted', color: '#8b8378' },
  { key: 'rejected', label: 'Rejected', color: '#b23b2c' },
];

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
    default:
      return 'bg-surface text-fg-muted';
  }
}

export function scoreTone(score: number): string {
  if (score >= 8) return 'text-accent';
  if (score >= 6) return 'text-warn';
  return 'text-danger';
}
