import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  linkedSignal,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { USE_MOCKS } from '../../core/api';
import { GenerateService } from '../../core/generate.service';
import { MOCK_JD_TEXT } from '../../core/mock-data';
import { CvSection, GeneratedCv, RequiredSkill } from '../../core/models';
import { ProfileService } from '../../core/profile.service';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';
import { BulletSelector } from './bullet-selector';

/** Rough one-page budget in characters. The server render loop is the real judge. */
const PAGE_BUDGET = 3000;

export interface Coverage {
  name: string;
  importance: number;
  required: boolean;
  /** Appears anywhere on the page, skills line included. What an ATS scan sees. */
  covered: boolean;
  /** Appears in a bullet or a project stack. What you can defend in an interview. */
  evidenced: boolean;
}

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

  /** The posting form owns the screen until there is a result, then collapses. */
  readonly editing = signal(false);
  readonly zoom = signal<'fit' | 'actual'>('fit');

  readonly form = this.fb.nonNullable.group({
    jd_text: ['', [Validators.required, Validators.minLength(80)]],
    company: [''],
    role: [''],
    title_variant: [''],
  });

  constructor() {
    // ?mock=<scenario> should show that state on load, not after you also paste
    // text and press Generate. Guarded by USE_MOCKS, and the mock-data import
    // breaks loudly when the fixtures are deleted, which is the cue to delete
    // this block too.
    if (USE_MOCKS && new URLSearchParams(location.search).has('mock') && !this.gen.result()) {
      this.form.patchValue({ jd_text: MOCK_JD_TEXT });
      this.generate();
    }
  }

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
   * What the posting asked for, against what the page actually says. Two levels,
   * because they answer different questions:
   *
   *   covered   somewhere on the page: skills line, stack, title, summary. What a
   *             keyword scan sees.
   *   evidenced named inside a bullet. What you can point at when asked to
   *             describe the work.
   *
   * A skill that is listed but not evidenced is the interview trap this whole
   * tool exists to avoid, so it gets its own colour rather than counting as a hit.
   *
   * ponytail: case-insensitive substring match. "React" hits "React Native", and
   * "ReactJS" in a posting misses "React" on the page. The synonym map planned
   * for `profile/skills_taxonomy.md` is the upgrade path.
   */
  readonly coverage = computed<Coverage[]>(() => {
    const jd = this.gen.result()?.parsed_jd;
    const cv = this.finalCv();
    if (!jd || !cv) {
      return [];
    }
    // Bullets only. A stack line is a list, same as the skills line, and listing
    // a technology is not the same as having a sentence that describes using it.
    const evidence = cv.sections
      .flatMap((s) => s.bullets.map((b) => b.text))
      .join(' ')
      .toLowerCase();
    const page = [
      evidence,
      cv.title,
      cv.summary,
      ...cv.skills_lines.flatMap((l) => l.items),
      ...cv.sections.flatMap((s) => s.stack),
    ]
      .join(' ')
      .toLowerCase();

    const check = (skill: RequiredSkill, required: boolean): Coverage => {
      const needle = skill.name.toLowerCase();
      return {
        name: skill.name,
        importance: skill.importance,
        required,
        covered: page.includes(needle),
        evidenced: evidence.includes(needle),
      };
    };

    return [
      ...jd.required_skills.map((s) => check(s, true)),
      ...jd.preferred_skills.map((s) => check(s, false)),
    ];
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

  /** Show the form full width until a result exists, or when reopened to edit. */
  readonly showForm = computed(() => this.editing() || !this.gen.result());

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
          this.editing.set(false);
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
    this.editing.set(false);
  }

  scoreTone(score: number): string {
    if (score >= 8) return 'text-accent';
    if (score >= 6) return 'text-warn';
    return 'text-danger';
  }
}
