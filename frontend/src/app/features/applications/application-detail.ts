import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, map, of, switchMap } from 'rxjs';

import { ApplicationsService } from '../../core/applications.service';
import { Coverage, computeCoverage } from '../../core/coverage';
import { ago, daysSince } from '../../core/dates';
import { APPLICATION_STATUSES, Application, ApplicationStatus, SentBullet } from '../../core/models';
import { SEGMENTS, inSegment, scoreTone, statusClass, waitingDays } from '../../core/pipeline';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

/**
 * Progression, left to right. Rejected and skipped sit outside it: one is the
 * employer's answer and the other is yours, and neither is a step forward.
 */
const TRACK: ApplicationStatus[] = ['saved', 'applied', 'replied', 'interview', 'offer'];

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
  private readonly router = inject(Router);
  private readonly sanitizer = inject(DomSanitizer);

  readonly statuses = APPLICATION_STATUSES;
  readonly track = TRACK;
  readonly ago = ago;
  readonly scoreTone = scoreTone;
  readonly statusClass = statusClass;
  readonly waitingDays = waitingDays;

  readonly saving = signal(false);
  readonly savedAt = signal<number | null>(null);
  readonly viewing = signal(false);
  readonly deleting = signal(false);
  /** TEMPORARY, with reexport(). Cache-buster so a rebuilt PDF actually shows. */
  readonly rebuilding = signal(false);
  readonly stamp = signal<number | null>(null);
  /** No export endpoint yet, so there is no file to frame. */
  readonly local = signal<Application | null>(null);

  private readonly loaded = toSignal<Application | null | undefined>(
    this.route.paramMap.pipe(
      map((params) => Number(params.get('id'))),
      switchMap((id) => this.api.get(id).pipe(catchError(() => of(null)))),
    ),
    { initialValue: undefined },
  );

  /** local wins once a change has been saved, so the view does not refetch. */
  readonly record = computed(() => this.local() ?? this.loaded());

  readonly ghosted = computed(() => {
    const current = this.record();
    return !!current && inSegment(current, 'ghosted');
  });

  /** Where it sits on the track, or -1 when it was rejected. */
  readonly stage = computed(() => {
    const current = this.record();
    return current ? TRACK.indexOf(current.status) : -1;
  });

  readonly segmentColor = computed(() => {
    const current = this.record();
    if (!current) {
      return '';
    }
    const key = SEGMENTS.find((s) => inSegment(current, s.key))?.color;
    return key ?? '#8b8378';
  });

  /**
   * Which of the posting's requirements a bullet on the page actually backed.
   *
   * ponytail: two states here, not the three on the generate page. The record
   * stores the bullets and the summary but not the skills line, so "on the page
   * but unbacked" cannot be told apart from "absent". Claiming otherwise would
   * be guessing, so the labels say backed / not backed and stop there.
   */
  readonly coverage = computed<Coverage[]>(() => {
    const current = this.record();
    if (!current) {
      return [];
    }
    const bullets = (current.selected_bullets ?? []).map((b) => b.text).join(' ');
    return computeCoverage(current.jd_parsed, bullets, `${bullets} ${current.summary_text}`);
  });

  readonly backed = computed(() => {
    const required = this.coverage().filter((c) => c.required);
    return { hit: required.filter((c) => c.evidenced).length, total: required.length };
  });

  /** Bullets grouped by the project they came from, in the order they printed. */
  readonly groups = computed<{ project: string; bullets: SentBullet[] }[]>(() => {
    const groups: { project: string; bullets: SentBullet[] }[] = [];
    for (const bullet of this.record()?.selected_bullets ?? []) {
      const last = groups.at(-1);
      if (last?.project === bullet.project_name) {
        last.bullets.push(bullet);
      } else {
        groups.push({ project: bullet.project_name, bullets: [bullet] });
      }
    }
    return groups;
  });

  readonly daysOut = computed(() => {
    const current = this.record();
    return current?.applied_at ? Math.floor(daysSince(current.applied_at)) : null;
  });

  setStatus(status: ApplicationStatus): void {
    const current = this.record();
    if (!current || current.status === status) {
      return;
    }
    this.save(current.id, { status }, `Marked as ${status}.`);
  }

  /** Saves on blur. Nothing to press, nothing to forget after a recruiter call. */
  saveNotes(current: Application, notes: string): void {
    const next = notes.trim() || null;
    if (next === (current.notes ?? null)) {
      return;
    }
    this.save(current.id, { notes: next }, 'Notes saved.');
  }

  private save(id: number, changes: Partial<Application>, message: string): void {
    this.saving.set(true);
    this.api.patch(id, changes).subscribe({
      next: (updated) => {
        this.local.set(updated);
        this.saving.set(false);
        this.savedAt.set(Date.now());
        this.toast.ok(message);
      },
      error: () => this.saving.set(false),
    });
  }

  /**
   * ponytail: native confirm(). It is one line, it cannot be clicked past by
   * accident, and this is the only destructive action in the app. A styled
   * dialog is worth building the day there is a second one.
   */
  remove(current: Application): void {
    const what = current.has_pdf ? ', and the CV that was sent with it,' : '';
    if (!confirm(`Delete ${current.company} - ${current.role}${what} permanently?`)) {
      return;
    }
    this.deleting.set(true);
    this.api.delete(current.id).subscribe({
      next: () => {
        this.toast.ok('Application deleted.');
        this.router.navigate(['/applications']);
      },
      error: () => this.deleting.set(false),
    });
  }

  /**
   * TEMPORARY, paired with POST /api/reexport. For rows whose PDF was printed
   * by an older version of the template. Delete with the route.
   */
  reexport(current: Application): void {
    this.rebuilding.set(true);
    this.api.reexport(current.id).subscribe({
      next: (res) => {
        this.rebuilding.set(false);
        // Same URL, new bytes. Without this the browser serves the old file
        // from cache and the button looks like it did nothing.
        this.stamp.set(Date.now());
        this.toast.ok(`Rebuilt ${res.filename}.`);
      },
      error: () => this.rebuilding.set(false),
    });
  }

  /** Angular blocks iframe src bindings. The URL is our own API plus a numeric id. */
  safePdfUrl(id: number): SafeResourceUrl {
    return this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfUrl(id));
  }

  pdfUrl(id: number): string {
    const stamp = this.stamp();
    return stamp ? `${this.api.pdfUrl(id)}?v=${stamp}` : this.api.pdfUrl(id);
  }

  /**
   * ponytail: native <dialog> plus an iframe. The browser already has a PDF
   * viewer, so embedding one would be a dependency for something built in.
   */
  openPdf(dialog: HTMLDialogElement): void {
    this.viewing.set(true);
    dialog.showModal();
  }

  closePdf(dialog: HTMLDialogElement): void {
    dialog.close();
    this.viewing.set(false);
  }
}
