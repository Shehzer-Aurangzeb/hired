import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, map, of, switchMap } from 'rxjs';

import { ApplicationsService } from '../../core/applications.service';
import { APPLICATION_STATUSES, Application, ApplicationStatus } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

/**
 * The interview-prep view. Months after applying this is where you see exactly
 * what they read: the posting, the parsed requirements, the score and the gaps.
 */
@Component({
  selector: 'app-application-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon],
  templateUrl: './application-detail.html',
})
export class ApplicationDetail {
  private readonly api = inject(ApplicationsService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);

  readonly statuses = APPLICATION_STATUSES;
  readonly saving = signal(false);
  readonly local = signal<Application | null>(null);

  private readonly loaded = toSignal<Application | null | undefined>(
    this.route.paramMap.pipe(
      map((params) => Number(params.get('id'))),
      switchMap((id) => this.api.get(id).pipe(catchError(() => of(null)))),
    ),
    { initialValue: undefined },
  );

  /** local wins once a status change has been saved, so the view does not refetch. */
  application(): Application | null | undefined {
    return this.local() ?? this.loaded();
  }

  setStatus(status: ApplicationStatus): void {
    const current = this.application();
    if (!current || current.status === status) {
      return;
    }
    this.saving.set(true);
    this.api.updateStatus(current.id, status).subscribe({
      next: (updated) => {
        this.local.set(updated);
        this.saving.set(false);
        this.toast.ok(`Marked as ${status}.`);
      },
      error: () => this.saving.set(false),
    });
  }

  pdfUrl(id: number): string {
    return this.api.pdfUrl(id);
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
