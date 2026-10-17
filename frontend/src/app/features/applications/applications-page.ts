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
  funnel,
  isSent,
  Segment,
  inSegment,
  scoreTone,
  statusClass,
  streak,
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
  /** Which row has its status dropdown open. One at a time. */
  readonly editing = signal<number | null>(null);
  readonly TEN = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  readonly hovered = signal<Segment | null>(null);

  private readonly searchBox = viewChild<ElementRef<HTMLInputElement>>('searchBox');

  /** "/" focuses search. */
  onKey(event: KeyboardEvent): void {
    if (event.key !== '/') {
      return;
    }
    // target is document when nothing is focused, which has no closest()
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

  /** Writable copy so status changes update without refetching. */
  readonly rows = linkedSignal(() => this.loaded());

  readonly total = computed(() => (this.rows() ?? []).length);
  readonly sent = computed(() => (this.rows() ?? []).filter(isSent).length);

  // Daily target is a preference, so it lives in localStorage.

  private static readonly KEY = 'hired.daily-target';

  readonly target = signal(ApplicationsPage.readTarget());

  private static readTarget(): number {
    try {
      const saved = Number(localStorage.getItem(ApplicationsPage.KEY));
      return saved >= 1 && saved <= 50 ? Math.round(saved) : 3;
    } catch {
      // Throws in private windows or with blocked site data.
      return 3;
    }
  }

  setTarget(value: number): void {
    const target = Math.min(50, Math.max(1, Math.round(value || 0)));
    this.target.set(target);
    try {
      localStorage.setItem(ApplicationsPage.KEY, String(target));
    } catch {
      // Not saved; still works for this session.
    }
  }

  /** Applications sent today (local time), counted by applied_at, not when saved. */
  readonly today = computed(() => {
    const midnight = new Date();
    midnight.setHours(0, 0, 0, 0);
    return (this.rows() ?? []).filter(
      (a) => a.applied_at && new Date(a.applied_at) >= midnight,
    ).length;
  });

  readonly hitTarget = computed(() => this.today() >= this.target());

  /** One slot per application the target asks for; filled ones are done. */
  readonly slots = computed(() =>
    Array.from({ length: this.target() }, (_, i) => i < this.today()),
  );

  readonly streak = computed(() => streak(this.rows() ?? [], this.target()));

  /**
   * How many reached each stage, widest first. The widths are relative to the
   * top of the funnel, so the shape of the drop is the thing you read.
   */
  readonly funnel = computed(() => {
    const stages = funnel(this.rows() ?? []);
    const top = stages[0]?.count || 1;
    return stages.map((stage) => ({
      ...stage,
      // A floor, or a stage nobody reached becomes an invisible hairline and
      // the row reads as missing rather than as zero.
      width: stage.count ? Math.max(2, Math.round((stage.count / top) * 100)) : 0,
    }));
  });

  /** Left the funnel rather than stalled in it. Shown under it, not inside. */
  readonly ended = computed(() => {
    const rows = this.rows() ?? [];
    return {
      rejected: rows.filter((a) => a.status === 'rejected').length,
      skipped: rows.filter((a) => a.status === 'skipped').length,
    };
  });

  readonly targetPercent = computed(() =>
    Math.min(100, Math.round((this.today() / this.target()) * 100)),
  );

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
      // Newest first. Floating everything unanswered to the top buried the
      // posting you sent an hour ago under thirty-four you can do nothing
      // about, and the "waiting on a reply" card already filters to those.
      // Inside that filter, the longest wait leads: that list is a chase list.
      .sort((a, b) =>
        filter === 'ghosted'
          ? waitingDays(b) - waitingDays(a)
          : b.created_at.localeCompare(a.created_at),
      );
  });

  readonly inSegment = inSegment;
  readonly waitingDays = waitingDays;

  toggleFilter(segment: Segment): void {
    this.filter.update((current) => (current === segment ? 'all' : segment));
  }

  /** Clicking a row opens it, unless the click was on a control inside it. */
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
