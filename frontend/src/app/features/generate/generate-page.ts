import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  linkedSignal,
  signal,
} from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { of, switchMap, tap, finalize, catchError, debounceTime } from 'rxjs';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

import { GenerateService } from '../../core/generate.service';
import { Coverage, computeCoverage } from '../../core/coverage';
import { verdict, verdictClass, statusClass } from '../../core/pipeline';
import { ago } from '../../core/dates';
import { ApplicationsService } from '../../core/applications.service';
import { CvSection, GeneratedCv } from '../../core/models';
import { ProfileService } from '../../core/profile.service';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';
import { BulletSelector } from './bullet-selector';

/** Rough one-page budget in characters; the server makes the real call. */
const PAGE_BUDGET = 3000;

@Component({
  selector: 'app-generate-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, BulletSelector, Icon, RouterLink],
  templateUrl: './generate-page.html',
})
export class GeneratePage {
  private readonly fb = inject(FormBuilder);
  private readonly toast = inject(ToastService);
  private readonly applications = inject(ApplicationsService);
  private readonly router = inject(Router);
  readonly gen = inject(GenerateService);
  readonly profile = inject(ProfileService).profile;

  constructor() {
    // What this machine can answer with, so the picker offers only pulled models.
    this.gen.loadModels();
  }

  readonly editing = signal(false);
  private readonly sanitizer = inject(DomSanitizer);

  readonly zoom = signal<'fit' | 'actual'>('fit');

  readonly form = this.fb.nonNullable.group({
    jd_text: ['', [Validators.required, Validators.minLength(80)]],
  });

  /** Resets on a new result, but stays editable. */
  readonly sections = linkedSignal<CvSection[]>(() =>
    (this.gen.result()?.cv.sections ?? []).map((s) => ({ ...s, bullets: [...s.bullets] })),
  );

  readonly excluded = linkedSignal<unknown, Set<string>>({
    source: () => this.gen.result(),
    computation: () => new Set<string>(),
  });

  /** What gets exported: current order, exclusions applied. */
  readonly finalCv = computed<GeneratedCv | null>(() => {
    const result = this.gen.result();
    if (!result) {
      return null;
    }
    const excluded = this.excluded();
    return {
      ...result.cv,
      sections: this.sections()
        .map((section) => ({
          ...section,
          bullets: section.bullets.filter((b) => !excluded.has(b.id)),
        }))
        .filter((section) => section.bullets.length > 0),
    };
  });

  readonly selectedCount = computed(() =>
    this.finalCv()?.sections.reduce((n, s) => n + s.bullets.length, 0) ?? 0,
  );

  // Character estimate only, to warn early. The backend measures the real page.
  readonly pageLoad = computed(() => {
    const cv = this.finalCv();
    if (!cv) {
      return 0;
    }
    const body = cv.sections.flatMap((s) => s.bullets).reduce((n, b) => n + b.text.length, 0);
    return Math.round(((cv.summary.length + body) / PAGE_BUDGET) * 100);
  });

  /** Evidence is limited to bullets still selected on screen. */
  readonly coverage = computed<Coverage[]>(() => {
    const jd = this.gen.fit()?.parsed_jd;
    const cv = this.finalCv();
    if (!jd || !cv) {
      return [];
    }
    const onPage = new Set(cv.sections.flatMap((s) => s.bullets.map((b) => b.id)));
    const backing = (cv.coverage ?? []).map((c) => ({
      ...c,
      bullet_ids: c.bullet_ids.filter((id) => onPage.has(id)),
    }));
    const page = [
      ...cv.sections.flatMap((s) => s.bullets.map((b) => b.text)),
      cv.title,
      cv.summary,
      ...cv.skills_lines.flatMap((l) => l.items),
      ...cv.sections.flatMap((s) => s.stack),
    ].join(' ');
    return computeCoverage(jd, backing, page);
  });

  readonly requiredCovered = computed(() => {
    const required = this.coverage().filter((c) => c.required);
    return {
      hit: required.filter((c) => c.covered).length,
      evidenced: required.filter((c) => c.evidenced).length,
      total: required.length,
    };
  });

  /** Mentioned on the page but not backed by any bullet. */
  readonly unbacked = computed(() => this.coverage().filter((c) => c.covered && !c.evidenced));

  readonly coverageGroups = computed(() => [
    { label: 'Required', items: this.coverage().filter((c) => c.required) },
    { label: 'Preferred', items: this.coverage().filter((c) => !c.required) },
  ]);

  readonly blockers = computed(() =>
    (this.gen.result()?.flags ?? []).filter((f) => f.type === 'block'),
  );

  readonly warnings = computed(() =>
    (this.gen.result()?.flags ?? []).filter((f) => f.type === 'warn'),
  );

  readonly canExport = computed(
    () => this.selectedCount() > 0 && this.blockers().length === 0 && !this.gen.exporting(),
  );

  readonly jdLength = computed(() => this.form.controls.jd_text.value.length);

  readonly showForm = computed(() => this.editing() || !this.gen.fit());

  /** Scored, but no CV generated yet. */
  readonly deciding = computed(() => !!this.gen.fit() && !this.gen.result());

  /** Selection differs from what was suggested. */
  readonly edited = computed(() => {
    const suggested = this.gen.result()?.cv.sections ?? [];
    if (this.excluded().size > 0) {
      return true;
    }
    const order = (list: CvSection[]) =>
      list.map((s) => s.bullets.map((b) => b.id).join(',')).join('|');
    return order(suggested) !== order(this.sections());
  });

  /** Letter is 816px wide at 96dpi; the sheet renders at that width and scales. */
  readonly sheetScale = computed(() => (this.zoom() === 'fit' ? 0.62 : 1));

  /** Same HTML the PDF is printed from. Debounced, since every edit refetches. */
  private readonly previewHtml = toSignal(
    toObservable(this.finalCv).pipe(
      debounceTime(200),
      switchMap((cv) => (cv ? this.gen.preview(cv).pipe(catchError(() => of(''))) : of(''))),
    ),
    { initialValue: '' },
  );

  readonly sheet = computed<SafeHtml | null>(() => {
    const html = this.previewHtml();
    // Safe to bypass: this is our own server-rendered template, same as the PDF.
    return html ? this.sanitizer.bypassSecurityTrustHtml(html) : null;
  });

  /** PDF margins as padding. Keep in sync with MARGIN in render.py. */
  readonly sheetPad = '0.25in';

  /** One page of content: 11in minus two 0.25in margins, at 96dpi. */
  readonly PAGE = 1008;

  /** The iframe grows to fit its content so overflow past one page is visible. */
  readonly sheetHeight = signal(this.PAGE);

  fitSheet(event: Event): void {
    const frame = event.target as HTMLIFrameElement;
    const height = frame.contentDocument?.body?.scrollHeight;
    this.sheetHeight.set(Math.max(this.PAGE, height ?? this.PAGE));
  }

  readonly overflows = computed(() => this.sheetHeight() > this.PAGE);

  startEdit(): void {
    this.editing.set(true);
  }

  cancelEdit(): void {
    this.editing.set(false);
  }

  resetSelection(): void {
    const result = this.gen.result();
    if (!result) {
      return;
    }
    this.sections.set(result.cv.sections.map((s) => ({ ...s, bullets: [...s.bullets] })));
    this.excluded.set(new Set());
  }

  checkFit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.gen.checkFit(this.form.getRawValue().jd_text).subscribe({
      next: () => this.editing.set(false),
      error: () => {
        /* the error interceptor already shows a toast */
      },
    });
  }

  /** Save the posting without generating a CV. */
  keep(): void {
    this.save('skipped').subscribe({
      next: (row) => {
        this.toast.ok(`Kept ${row.company}. No CV was made for it.`);
        this.reset();
      },
      error: () => {},
    });
  }

  /** Saves the row first so export has something to attach the PDF to. */
  generate(): void {
    const fit = this.gen.fit();
    if (!fit) {
      return;
    }
    const existing = this.gen.applicationId();
    const row = existing ? of({ id: existing }) : this.save('saved');
    row
      .pipe(
        tap((created) => this.gen.applicationId.set(created.id)),
        switchMap(() =>
          this.gen.generate({
            jd_text: this.gen.jdText(),
            parsed_jd: fit.parsed_jd,
          }),
        ),
      )
      .subscribe({ error: () => {} });
  }

  /** Fixed list so reply rate can be grouped by source later. */
  readonly sources = ['LinkedIn', 'Indeed', 'Company website', 'Job Bank', 'Wellfound', 'Referral', 'Other'];

  // Remembered across postings, since you usually work one job board at a time.
  readonly source = signal(localStorage.getItem('hired.last-source') ?? 'LinkedIn');
  readonly url = signal('');

  setSource(value: string): void {
    this.source.set(value);
    try {
      localStorage.setItem('hired.last-source', value);
    } catch {
      // Ignore storage errors.
    }
  }

  private save(status: 'saved' | 'skipped') {
    const fit = this.gen.fit();
    this.gen.saving.set(true);
    return this.applications
      .create({
        company: fit?.parsed_jd.company || 'Unknown',
        role: fit?.parsed_jd.role || 'Unknown',
        source: this.source(),
        url: this.url().trim() || null,
        jd_text: this.gen.jdText(),
        jd_parsed: fit?.parsed_jd,
        fit_score: fit?.fit.score ?? 0,
        fit_reasoning: fit?.fit.reasoning ?? '',
        gaps: fit?.fit.gaps ?? [],
        // Saved beside the score, so a number can be read against the model
        // that produced it rather than guessed at months later.
        fit_model: fit?.model ?? '',
        status,
      })
      .pipe(finalize(() => this.gen.saving.set(false)));
  }

  readonly hasVariants = computed(() => (this.profile.value()?.titles.length ?? 0) > 1);

  /** Cycles to the next hand-written title and summary, kept as a pair. */
  nextVariant(): void {
    const profile = this.profile.value();
    const cv = this.gen.result()?.cv;
    if (!profile || !cv || profile.titles.length < 2) {
      return;
    }
    const at = profile.titles.findIndex((title) => title.text === cv.title);
    const next = profile.titles[(at + 1) % profile.titles.length];
    const summary = profile.summaries.find((s) => s.id === next.id);
    this.gen.useVariant(next.text, summary?.text ?? cv.summary);
    this.toast.ok(`Switched to the ${next.id} framing.`);
  }

  export(): void {
    const cv = this.finalCv();
    const id = this.gen.applicationId();
    if (!cv || id === null) {
      return;
    }
    this.gen.export(id, cv).subscribe({
      next: (res) => {
        this.exported.set(true);
        const pages = res.page_count === 1 ? 'one page' : `${res.page_count} pages`;
        this.toast.ok(`Saved ${res.filename}, ${pages}.`);
      },
      error: () => {},
    });
  }

  readonly exported = signal(false);

  /** Ask the model for a fresh selection against the same posting. */
  regenerate(): void {
    const fit = this.gen.fit();
    if (!fit || !this.canRegenerate()) {
      return;
    }
    if (this.edited() && !confirm('This replaces the selection, including your edits. Go ahead?')) {
      return;
    }
    this.gen
      .generate({
        jd_text: this.gen.jdText(),
        parsed_jd: fit.parsed_jd,
      })
      // The exported PDF is now older than what is on screen.
      .subscribe({ next: () => this.exported.set(false), error: () => {} });
  }

  readonly applied = signal(false);

  /** Named on the page when it is not the model you configured. */
  readonly servedBy = computed(() => this.gen.result()?.model ?? this.gen.fit()?.model ?? '');

  readonly canRegenerate = computed(
    () => !!this.gen.result() && !this.gen.generating() && !this.gen.exporting() && !this.applied(),
  );

  /** applied_at is stamped once and never overwritten. */
  markApplied(): void {
    const id = this.gen.applicationId();
    if (id === null) {
      return;
    }
    this.applications.patch(id, { status: 'applied' }).subscribe({
      next: () => {
        this.applied.set(true);
        this.toast.ok('Marked as applied.');
        this.router.navigate(['/applications', id]);
      },
      error: () => {},
    });
  }

  reset(): void {
    this.gen.clear();
    this.form.reset();
    this.editing.set(false);
    this.exported.set(false);
    this.applied.set(false);
  }

  readonly verdict = verdict;
  readonly statusClass = statusClass;
  readonly ago = ago;
  readonly verdictClass = verdictClass;

  scoreTone(score: number): string {
    if (score >= 8) return 'text-accent';
    if (score >= 6) return 'text-warn';
    return 'text-danger';
  }
}
