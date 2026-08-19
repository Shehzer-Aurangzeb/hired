/** "6 days ago" from an ISO string. Intl does the wording, no dependency. */
const RELATIVE = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 86_400_000],
  ['month', 30 * 86_400_000],
  ['week', 7 * 86_400_000],
  ['day', 86_400_000],
  ['hour', 3_600_000],
  ['minute', 60_000],
];

export function ago(iso: string | null): string {
  if (!iso) {
    return '';
  }
  const delta = Date.parse(iso) - Date.now();
  for (const [unit, ms] of UNITS) {
    if (Math.abs(delta) >= ms) {
      return RELATIVE.format(Math.round(delta / ms), unit);
    }
  }
  return 'just now';
}

export function daysSince(iso: string | null): number {
  return iso ? (Date.now() - Date.parse(iso)) / 86_400_000 : 0;
}
