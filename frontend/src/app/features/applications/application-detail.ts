import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, map, of, switchMap } from 'rxjs';

import { ApplicationsService } from '../../core/applications.service';
import { Coverage, computeCoverage } from '../../core/coverage';
import { ago, daysSince } from '../../core/dates';
import {
  APPLICATION_STATUSES,
  Application,
  ApplicationStatus,
  Artifact,
  SentBullet,
} from '../../core/models';
import { SEGMENTS, inSegment, scoreTone, statusClass, waitingDays } from '../../core/pipeline';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

/** Forward stages only; rejected and skipped are not steps. */
const TRACK: ApplicationStatus[] = ['saved', 'applied', 'replied', 'interview', 'offer'];

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
  /** Temporary, with reexport(). `stamp` busts the cache so a rebuilt PDF shows. */
  readonly rebuilding = signal(false);
  readonly stamp = signal<number | null>(null);
  readonly local = signal<Application | null>(null);

  /** Which kind is being written, or null. One at a time: each is a model call. */
  readonly writing = signal<'email' | 'answer' | null>(null);
  readonly question = signal('');
  /** The one just written, editable before you copy it. Edits are for the copy;
   *  what is kept on the row is what the model actually wrote. */
  readonly draft = signal<Artifact | null>(null);
  readonly edited = signal('');
  readonly copied = signal(false);

  private readonly loaded = toSignal<Application | null | undefined>(
    this.route.paramMap.pipe(
      map((params) => Number(params.get('id'))),
      switchMap((id) => this.api.get(id).pipe(catchError(() => of(null)))),
    ),
    { initialValue: undefined },
  );

  /** Local copy wins after a save, so there is no refetch. */
  readonly record = computed(() => this.local() ?? this.loaded());

  readonly ghosted = computed(() => {
    const current = this.record();
    return !!current && inSegment(current, 'ghosted');
  });

  /** Index on the track, or -1 when rejected. */
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

  /** Only backed / not backed here: the record does not store the skills line. */
  readonly coverage = computed<Coverage[]>(() => {
    const current = this.record();
    if (!current) {
      return [];
    }
    const bullets = (current.selected_bullets ?? []).map((b) => b.text).join(' ');
    return computeCoverage(
      current.jd_parsed,
      current.coverage ?? [],
      `${bullets} ${current.summary_text}`,
    );
  });

  /** Older rows have no coverage stored; treat that as unknown, not zero. */
  readonly unrecorded = computed(() => {
    const current = this.record();
    return !!current?.selected_bullets?.length && !current.coverage?.length;
  });

  readonly backed = computed(() => {
    const required = this.coverage().filter((c) => c.required);
    return { hit: required.filter((c) => c.evidenced).length, total: required.length };
  });

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

  /** Saves on blur. */
  /** Newest first, and never the one still open as a draft. */
  readonly written = computed(() => [...(this.record()?.artifacts ?? [])].reverse());

  write(id: number, kind: 'email' | 'answer'): void {
    const question = this.question().trim();
    if (kind === 'answer' && !question) {
      this.toast.error('Paste the question the form is asking first.');
      return;
    }
    this.writing.set(kind);
    this.copied.set(false);
    this.api.writeArtifact(id, { kind, question }).subscribe({
      next: (made) => {
        this.draft.set(made);
        this.edited.set(made.body);
        this.writing.set(null);
        // Keep the row in step without a refetch, as saving does.
        const current = this.record();
        if (current) {
          this.local.set({ ...current, artifacts: [...current.artifacts, made] });
        }
      },
      error: () => this.writing.set(null),
    });
  }

  copy(text: string): void {
    navigator.clipboard.writeText(text).then(
      () => {
        this.copied.set(true);
        setTimeout(() => this.copied.set(false), 2000);
      },
      () => this.toast.error('Could not reach the clipboard.'),
    );
  }

  reopen(made: Artifact): void {
    this.draft.set(made);
    this.edited.set(made.body);
    this.copied.set(false);
  }

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

  /** Temporary: remove with POST /api/reexport. */
  reexport(current: Application): void {
    this.rebuilding.set(true);
    this.api.reexport(current.id).subscribe({
      next: (res) => {
        this.rebuilding.set(false);
        // Same URL, new file, so bust the browser cache.
        this.stamp.set(Date.now());
        if (res.dropped?.length) {
          // Rebuilding against an edited profile can drop bullets; say which.
          this.toast.error(
            `Rebuilt without ${res.dropped.length} bullet(s) no longer in your profile: ` +
              res.dropped.join(', '),
          );
        } else {
          this.toast.ok(`Rebuilt ${res.filename}.`);
        }
      },
      error: () => this.rebuilding.set(false),
    });
  }

  /** Angular blocks iframe src bindings; safe because this is our own API URL. */
  safePdfUrl(id: number): SafeResourceUrl {
    return this.sanitizer.bypassSecurityTrustResourceUrl(this.pdfUrl(id));
  }

  pdfUrl(id: number): string {
    const stamp = this.stamp();
    return stamp ? `${this.api.pdfUrl(id)}?v=${stamp}` : this.api.pdfUrl(id);
  }

  openPdf(dialog: HTMLDialogElement): void {
    this.viewing.set(true);
    dialog.showModal();
  }

  closePdf(dialog: HTMLDialogElement): void {
    dialog.close();
    this.viewing.set(false);
  }
}
