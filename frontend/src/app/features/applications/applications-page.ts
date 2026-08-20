import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';

import { ApplicationsService } from '../../core/applications.service';
import { ago, daysSince } from '../../core/dates';
import { Application, ApplicationStatus } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

/** Sitting in Applied this long with no reply means it needs chasing. */
const FOLLOW_UP_DAYS = 10;

/**
 * Segments double as the filter, so the legend is the only status control on the
 * page. `waiting` and `ghosted` are both status 'applied'; the split is derived
 * from how long it has been sitting.
 */
export type Segment =
  | 'generated'
  | 'waiting'
  | 'replied'
  | 'interview'
  | 'offer'
  | 'ghosted'
  | 'rejected';

export type Filter = 'all' | Segment;

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
const SEGMENTS: { key: Segment; label: string; color: string; hatched?: boolean }[] = [
  { key: 'generated', label: 'Not sent', color: '#b9ae95', hatched: true },
  { key: 'waiting', label: 'Waiting', color: '#3a6ea8' },
  { key: 'replied', label: 'Replied', color: '#a86a08' },
  { key: 'interview', label: 'Interview', color: '#0a7f66' },
  { key: 'offer', label: 'Offer', color: '#6b4fa8' },
  { key: 'ghosted', label: 'Ghosted', color: '#8b8378' },
  { key: 'rejected', label: 'Rejected', color: '#b23b2c' },
];

@Component({
  selector: 'app-applications-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon],
  templateUrl: './applications-page.html',
})
export class ApplicationsPage {
  private readonly api = inject(ApplicationsService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  readonly statuses: ApplicationStatus[] = [
    'generated',
    'applied',
    'replied',
    'interview',
    'rejected',
    'offer',
  ];
  readonly query = signal('');
  readonly filter = signal<Filter>('all');
  readonly saving = signal<number | null>(null);

  private readonly loaded = toSignal<Application[] | null>(
    this.api.list().pipe(catchError(() => of<Application[]>([]))),
    { initialValue: null },
  );

  /** Writable copy, so a status change updates the row without refetching. */
  readonly rows = linkedSignal(() => this.loaded());

  readonly total = computed(() => (this.rows() ?? []).length);
  readonly sent = computed(() => (this.rows() ?? []).filter((a) => a.status !== 'generated').length);

  /** Of everything actually sent, how much came back. */
  readonly replyRate = computed(() => {
    const sent = this.sent();
    if (!sent) {
      return null;
    }
    const heard = (this.rows() ?? []).filter((a) =>
      ['replied', 'interview', 'offer'].includes(a.status),
    ).length;
    return Math.round((heard / sent) * 100);
  });

  readonly pipeline = computed(() => {
    const list = this.rows() ?? [];
    return SEGMENTS.map((segment) => {
      const count = list.filter((a) => this.inSegment(a, segment.key)).length;
      return { ...segment, count, pct: list.length ? (count / list.length) * 100 : 0 };
    });
  });

  readonly stale = computed(() => (this.rows() ?? []).filter((a) => this.inSegment(a, 'ghosted')));

  readonly visible = computed(() => {
    const query = this.query().trim().toLowerCase();
    const filter = this.filter();
    return (this.rows() ?? [])
      .filter(
        (a) =>
          (filter === 'all' || this.inSegment(a, filter)) &&
          (!query ||
            a.company.toLowerCase().includes(query) ||
            a.role.toLowerCase().includes(query)),
      )
      // Anything waiting on a reply floats up. That is the point of the list.
      .sort((a, b) => {
        const chase = Number(this.inSegment(b, 'ghosted')) - Number(this.inSegment(a, 'ghosted'));
        return chase || b.created_at.localeCompare(a.created_at);
      });
  });

  inSegment(application: Application, segment: Segment): boolean {
    if (segment === 'ghosted') {
      return application.status === 'applied' && this.waitingDays(application) > FOLLOW_UP_DAYS;
    }
    if (segment === 'waiting') {
      return application.status === 'applied' && this.waitingDays(application) <= FOLLOW_UP_DAYS;
    }
    return application.status === segment;
  }

  waitingDays(application: Application): number {
    return Math.floor(daysSince(application.applied_at));
  }

  toggleFilter(segment: Segment): void {
    this.filter.update((current) => (current === segment ? 'all' : segment));
  }

  /** The whole row opens the record, except where a real control lives. */
  openRow(event: Event, id: number): void {
    if ((event.target as HTMLElement).closest('a, button, select, input, label')) {
      return;
    }
    this.router.navigate(['/applications', id]);
  }

  setStatus(application: Application, status: string): void {
    if (status === application.status) {
      return;
    }
    this.saving.set(application.id);
    this.api.patch(application.id, { status: status as ApplicationStatus }).subscribe({
      next: (updated) => {
        this.rows.update((list) => (list ?? []).map((a) => (a.id === updated.id ? updated : a)));
        this.saving.set(null);
        this.toast.ok(`${updated.company} marked as ${status}.`);
      },
      error: () => this.saving.set(null),
    });
  }

  readonly ago = ago;

  statusClass(status: ApplicationStatus): string {
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

  scoreTone(score: number): string {
    if (score >= 8) return 'text-accent';
    if (score >= 6) return 'text-warn';
    return 'text-danger';
  }
}
