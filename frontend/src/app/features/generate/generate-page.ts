import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { GenerateService } from '../../core/generate.service';
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
  imports: [ReactiveFormsModule, BulletSelector, Icon],
  templateUrl: './generate-page.html',
})
export class GeneratePage {
  private readonly fb = inject(FormBuilder);
  private readonly toast = inject(ToastService);
  readonly gen = inject(GenerateService);
  readonly profile = inject(ProfileService).profile;

  readonly form = this.fb.nonNullable.group({
    jd_text: ['', [Validators.required, Validators.minLength(80)]],
    company: [''],
    role: [''],
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

  generate(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    this.gen
      .generate({
        jd_text: raw.jd_text,
        company: raw.company || undefined,
        role: raw.role || undefined,
        title_variant: raw.title_variant || undefined,
      })
      .subscribe({
        next: (res) => {
          this.form.patchValue(
            { company: res.parsed_jd.company, role: res.parsed_jd.role },
            { emitEvent: false },
          );
        },
        error: () => {
          /* the error interceptor already raised a toast */
        },
      });
  }

  regenerateSummary(): void {
    const variant = this.form.controls.title_variant.value || 'fullstack';
    this.gen.regenerateSummary(variant).subscribe({
      next: () => this.toast.ok('Summary regenerated.'),
      error: () => {},
    });
  }

  export(): void {
    const cv = this.finalCv();
    if (!cv) {
      return;
    }
    this.gen.export(cv).subscribe({
      next: (res) =>
        this.toast.ok(`Exported ${res.filename} (${res.page_count} page).`),
      error: () => {},
    });
  }

  reset(): void {
    this.gen.clear();
    this.form.reset();
  }

  scoreTone(score: number): string {
    if (score >= 8) return 'text-accent';
    if (score >= 6) return 'text-warn';
    return 'text-danger';
  }
}
