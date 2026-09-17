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

/** Rough one-page budget in characters. The server render loop is the real judge. */
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

  /** The posting form owns the screen until there is a result, then collapses. */
  readonly editing = signal(false);
  private readonly sanitizer = inject(DomSanitizer);

  readonly zoom = signal<'fit' | 'actual'>('fit');

  readonly form = this.fb.nonNullable.group({
    jd_text: ['', [Validators.required, Validators.minLength(80)]],
    title_variant: [''],
  });

  /**
   * linkedSignal, so a fresh generation resets the edits but the user can still
   * reorder and deselect against the current result.
   */
  readonly sections = linkedSignal<CvSection[]>(() =>
    (this.gen.result()?.cv.sections ?? []).map((s) => ({ ...s, bullets: [...s.bullets] })),
  );

  readonly excluded = linkedSignal<unknown, Set<string>>({
    source: () => this.gen.result(),
    computation: () => new Set<string>(),
  });

  /** What actually gets exported: current order, exclusions applied. */
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

  // ponytail: character heuristic, not a real measurement. The render-and-measure
  // loop in the backend decides. This only exists to warn before an export round trip.
  readonly pageLoad = computed(() => {
    const cv = this.finalCv();
    if (!cv) {
      return 0;
    }
    const body = cv.sections.flatMap((s) => s.bullets).reduce((n, b) => n + b.text.length, 0);
    return Math.round(((cv.summary.length + body) / PAGE_BUDGET) * 100);
  });

  /**
   * Bullets carry the evidence; the skills line and stacks only make it visible.
   *
   * The selector said which bullets back which requirement, but the person can
   * still deselect one here, so the map is narrowed to what is left on screen.
   */
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

  /** Listed on the page with no bullet behind it. The interview risk. */
  readonly unbacked = computed(() => this.coverage().filter((c) => c.covered && !c.evidenced));

  /** Required and preferred read differently, so they are not one flat list. */
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

  private readonly variantId = toSignal(this.form.controls.title_variant.valueChanges, {
    initialValue: '',
  });

  /** The headline itself, so the select is not three opaque ids. */
  readonly variantText = computed(
    () => this.profile.value()?.titles.find((t) => t.id === this.variantId())?.text ?? '',
  );

  /** The posting owns the screen until it has been scored, or when reopened. */
  readonly showForm = computed(() => this.editing() || !this.gen.fit());

  /** Scored, but no CV asked for yet. The decision point. */
  readonly deciding = computed(() => !!this.gen.fit() && !this.gen.result());

  /** Has the selection drifted from what the selector suggested. */
  readonly edited = computed(() => {
    const suggested = this.gen.result()?.cv.sections ?? [];
    if (this.excluded().size > 0) {
      return true;
    }
    const order = (list: CvSection[]) =>
      list.map((s) => s.bullets.map((b) => b.id).join(',')).join('|');
    return order(suggested) !== order(this.sections());
  });

  /** Letter is 816px at 96dpi. The sheet renders at that width and is zoomed. */
  readonly sheetScale = computed(() => (this.zoom() === 'fit' ? 0.62 : 1));

  /**
   * The preview is the PDF's own HTML, fetched and shown in an iframe.
   *
   * It used to be Tailwind markup in this template approximating the layout, and
   * an approximation of a layout is a layout that silently stops matching. This
   * cannot: it is the same render_html the exporter prints from.
   *
   * Debounced because it refires on every reorder and deselect, and each one is
   * a round trip.
   */
  private readonly previewHtml = toSignal(
    toObservable(this.finalCv).pipe(
      debounceTime(200),
      switchMap((cv) => (cv ? this.gen.preview(cv).pipe(catchError(() => of(''))) : of(''))),
    ),
    { initialValue: '' },
  );

  readonly sheet = computed<SafeHtml | null>(() => {
    const html = this.previewHtml();
    // Our own template, rendered by our own server from our own profile. The
    // bypass is what lets it into an iframe at all; nothing user-authored
    // reaches it that does not already reach the PDF.
    return html ? this.sanitizer.bypassSecurityTrustHtml(html) : null;
  });

  /** The margins page.pdf applies, as padding, so the sheet matches the print.
      Mirrors MARGIN in render.py; move one and move the other. */
  readonly sheetPad = '0.25in';

  /** 11in less the two 0.25in margins, at 96dpi. One page of content. */
  readonly PAGE = 1008;

  /**
   * The iframe is sized to its content, so a page and a bit shows as a page and
   * a bit instead of being silently cropped at the fold. The renderer is allowed
   * up to 1.25 pages, so overflow is a normal state to look at, not an error.
   */
  readonly sheetHeight = signal(this.PAGE);

  fitSheet(event: Event): void {
    const frame = event.target as HTMLIFrameElement;
    const height = frame.contentDocument?.body?.scrollHeight;
    this.sheetHeight.set(Math.max(this.PAGE, height ?? this.PAGE));
  }

  /** Where page one ends, drawn on the sheet. The question is always "does it fit". */
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
        /* the error interceptor already raised a toast */
      },
    });
  }

  /**
   * Keep the posting without applying to it. Often the more valuable record:
   * what it exposed is a gap you now know about, and no CV was ever needed.
   */
  keep(): void {
    this.save('skipped').subscribe({
      next: (row) => {
        this.toast.ok(`Kept ${row.company}. No CV was made for it.`);
        this.reset();
      },
      error: () => {},
    });
  }

  /**
   * Ask for a CV. The row is created first so export has something to attach a
   * PDF to, and so a generation you abandon still leaves the posting on record.
   */
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
            title_variant: this.form.getRawValue().title_variant || undefined,
          }),
        ),
      )
      .subscribe({ error: () => {} });
  }

  /**
   * Where the posting came from. Fixed list rather than free text, because the
   * whole point is grouping reply rate by it later, and "LinkedIn" typed three
   * ways is three sources.
   */
  readonly sources = ['LinkedIn', 'Indeed', 'Company website', 'Job Bank', 'Wellfound', 'Referral', 'Other'];

  // Asked for on the decide screen, which is the only moment the tab is still
  // open. Remembered across postings: you tend to work one board at a time.
  readonly source = signal(localStorage.getItem('hired.last-source') ?? 'LinkedIn');
  readonly url = signal('');

  setSource(value: string): void {
    this.source.set(value);
    try {
      localStorage.setItem('hired.last-source', value);
    } catch {
      // Not worth failing a save over a remembered dropdown.
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
        status,
      })
      .pipe(finalize(() => this.gen.saving.set(false)));
  }

  /** More than one framing to switch between. One is not a choice. */
  readonly hasVariants = computed(() => (this.profile.value()?.titles.length ?? 0) > 1);

  /**
   * Cycle to the next headline and summary you wrote, keeping the pair together:
   * they are written per framing and reading a front-end summary under a
   * full-stack headline is worse than either alone. Nothing is generated.
   */
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

  /** The employer has it. Stamped once, and never rewritten by a later stage. */
  markApplied(): void {
    const id = this.gen.applicationId();
    if (id === null) {
      return;
    }
    this.applications.patch(id, { status: 'applied' }).subscribe({
      next: () => {
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
