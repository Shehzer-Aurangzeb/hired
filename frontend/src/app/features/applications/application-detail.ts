import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, map, of, switchMap } from 'rxjs';

import { USE_MOCKS } from '../../core/api';
import { ApplicationsService } from '../../core/applications.service';
import { Coverage, computeCoverage } from '../../core/coverage';
import { ago, daysSince } from '../../core/dates';
import { APPLICATION_STATUSES, Application, ApplicationStatus, SentBullet } from '../../core/models';
import { SEGMENTS, inSegment, scoreTone, statusClass, waitingDays } from '../../core/pipeline';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

/** Progression, left to right. Rejected sits outside it as a terminal state. */
const TRACK: ApplicationStatus[] = ['generated', 'applied', 'replied', 'interview', 'offer'];

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
  /** No export endpoint yet, so there is no file to frame. */
  readonly mocked = USE_MOCKS;
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

  /** Angular blocks iframe src bindings. The URL is our own API plus a numeric id. */
  safePdfUrl(id: number): SafeResourceUrl {
    return this.sanitizer.bypassSecurityTrustResourceUrl(this.api.pdfUrl(id));
  }

  pdfUrl(id: number): string {
    return this.api.pdfUrl(id);
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
