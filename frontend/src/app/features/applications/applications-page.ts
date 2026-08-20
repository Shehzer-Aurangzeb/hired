import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';

import { ApplicationsService } from '../../core/applications.service';
import { ago, daysSince } from '../../core/dates';
import { APPLICATION_STATUSES, Application, ApplicationStatus } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

type Filter = 'all' | ApplicationStatus;

/** Sitting in Applied this long with no reply means it needs chasing. */
const FOLLOW_UP_DAYS = 10;

@Component({
  selector: 'app-applications-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon],
  templateUrl: './applications-page.html',
})
export class ApplicationsPage {
  private readonly api = inject(ApplicationsService);
  private readonly toast = inject(ToastService);

  readonly statuses = APPLICATION_STATUSES;
  readonly filters: Filter[] = ['all', ...APPLICATION_STATUSES];
  readonly query = signal('');
  readonly filter = signal<Filter>('all');
  readonly saving = signal<number | null>(null);

  /** toSignal, not httpResource, because this is a one-shot load with no reactive URL. */
  private readonly loaded = toSignal<Application[] | null>(
    this.api.list().pipe(catchError(() => of<Application[]>([]))),
    { initialValue: null },
  );

  /** Writable copy, so a status change updates the row without refetching. */
  readonly rows = linkedSignal(() => this.loaded());

  readonly counts = computed(() => {
    const list = this.rows() ?? [];
    const counts = new Map<Filter, number>([['all', list.length]]);
    for (const status of this.statuses) {
      counts.set(status, list.filter((a) => a.status === status).length);
    }
    return counts;
  });

  readonly stale = computed(() => (this.rows() ?? []).filter((a) => this.needsFollowUp(a)));

  readonly visible = computed(() => {
    const query = this.query().trim().toLowerCase();
    const filter = this.filter();
    return (this.rows() ?? [])
      .filter(
        (a) =>
          (filter === 'all' || a.status === filter) &&
          (!query ||
            a.company.toLowerCase().includes(query) ||
            a.role.toLowerCase().includes(query)),
      )
      // Anything waiting on a reply floats up. That is the whole point of the list.
      .sort((a, b) => {
        const chase = Number(this.needsFollowUp(b)) - Number(this.needsFollowUp(a));
        return chase || b.created_at.localeCompare(a.created_at);
      });
  });

  needsFollowUp(application: Application): boolean {
    return application.status === 'applied' && this.waitingDays(application) > FOLLOW_UP_DAYS;
  }

  waitingDays(application: Application): number {
    return Math.floor(daysSince(application.applied_at));
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
