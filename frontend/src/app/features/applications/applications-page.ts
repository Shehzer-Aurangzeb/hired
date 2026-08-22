import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  linkedSignal,
  signal,
  viewChild,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { DecimalPipe } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';

import { ApplicationsService } from '../../core/applications.service';
import { ago } from '../../core/dates';
import { Application, ApplicationStatus } from '../../core/models';
import {
  SEGMENTS,
  isSent,
  Segment,
  inSegment,
  scoreTone,
  statusClass,
  waitingDays,
} from '../../core/pipeline';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

@Component({
  selector: 'app-applications-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon, DecimalPipe],
  templateUrl: './applications-page.html',
  host: { '(document:keydown)': 'onKey($event)' },
})
export class ApplicationsPage {
  private readonly api = inject(ApplicationsService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  readonly statuses: ApplicationStatus[] = [
    'saved',
    'skipped',
    'applied',
    'replied',
    'interview',
    'rejected',
    'offer',
  ];
  readonly query = signal('');
  readonly filter = signal<'all' | Segment>('all');
  readonly saving = signal<number | null>(null);
  /** Which band segment the pointer is over, so the others can recede. */
  readonly hovered = signal<Segment | null>(null);

  private readonly searchBox = viewChild<ElementRef<HTMLInputElement>>('searchBox');

  /** Slash focuses search, the way every tool with a list does it. */
  onKey(event: KeyboardEvent): void {
    if (event.key !== '/') {
      return;
    }
    // target is document when nothing is focused, and document has no closest()
    const target = event.target;
    if (target instanceof HTMLElement && target.closest('input, textarea, select')) {
      return;
    }
    event.preventDefault();
    this.searchBox()?.nativeElement.focus();
  }

  segmentOpacity(key: Segment): number {
    const hovered = this.hovered();
    return !hovered || hovered === key ? 1 : 0.35;
  }

  private readonly loaded = toSignal<Application[] | null>(
    this.api.list().pipe(catchError(() => of<Application[]>([]))),
    { initialValue: null },
  );

  /** Writable copy, so a status change updates the row without refetching. */
  readonly rows = linkedSignal(() => this.loaded());

  readonly total = computed(() => (this.rows() ?? []).length);
  readonly sent = computed(() => (this.rows() ?? []).filter(isSent).length);

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

  readonly inSegment = inSegment;
  readonly waitingDays = waitingDays;

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

  readonly statusClass = statusClass;
  readonly scoreTone = scoreTone;
}
