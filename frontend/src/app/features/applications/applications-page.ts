import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';

import { ApplicationsService } from '../../core/applications.service';
import { APPLICATION_STATUSES, Application, ApplicationStatus } from '../../core/models';
import { Icon } from '../../shared/icon';

type Filter = 'all' | ApplicationStatus;

@Component({
  selector: 'app-applications-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon],
  templateUrl: './applications-page.html',
})
export class ApplicationsPage {
  private readonly api = inject(ApplicationsService);

  readonly statuses = APPLICATION_STATUSES;
  readonly filters: Filter[] = ['all', ...APPLICATION_STATUSES];
  readonly query = signal('');
  readonly filter = signal<Filter>('all');

  /** toSignal, not httpResource, because this is a one-shot load with no reactive URL. */
  readonly applications = toSignal<Application[] | null>(
    this.api.list().pipe(catchError(() => of<Application[]>([]))),
    { initialValue: null },
  );

  readonly counts = computed(() => {
    const list = this.applications() ?? [];
    const counts = new Map<Filter, number>([['all', list.length]]);
    for (const status of this.statuses) {
      counts.set(status, list.filter((a) => a.status === status).length);
    }
    return counts;
  });

  readonly visible = computed(() => {
    const query = this.query().trim().toLowerCase();
    const filter = this.filter();
    return (this.applications() ?? []).filter(
      (a) =>
        (filter === 'all' || a.status === filter) &&
        (!query ||
          a.company.toLowerCase().includes(query) ||
          a.role.toLowerCase().includes(query)),
    );
  });

  /** Anything sitting in Applied for more than ten days needs a follow-up. */
  stale(application: Application): boolean {
    if (application.status !== 'applied' || !application.applied_at) {
      return false;
    }
    const days = (Date.now() - Date.parse(application.applied_at)) / 86_400_000;
    return days > 10;
  }

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
