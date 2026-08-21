import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { MAX_BYTES } from '../../core/api';
import { copyPrompt, openClaude } from '../../core/claude-draft';
import { ProfileService } from '../../core/profile.service';
import { ToastService } from '../../core/toast.service';
import { ProfileIssue, ValidationResult } from '../../core/models';
import { Icon } from '../../shared/icon';

type Source = 'paste' | 'upload' | 'template';

@Component({
  selector: 'app-onboarding-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  templateUrl: './onboarding-page.html',
})
export class OnboardingPage {
  private readonly profile = inject(ProfileService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  readonly source = signal<Source | null>(null);
  readonly text = signal('');
  readonly result = signal<ValidationResult | null>(null);
  readonly checking = signal(false);
  readonly saving = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly fileName = signal<string | null>(null);
  /** Backend config, fetched with the template it belongs to. */
  readonly prompt = signal('');
  readonly copied = signal(false);

  readonly lines = computed(() => this.text().split('\n'));
  readonly lineNumbers = computed(() => this.lines().map((_, i) => i + 1));
  readonly errorLines = computed(
    () => new Set((this.result()?.errors ?? []).map((e) => e.line).filter(Boolean)),
  );
  readonly canSave = computed(
    () => !!this.result()?.ok && !this.saving() && this.text().trim().length > 0,
  );

  choose(source: Source): void {
    this.source.set(source);
    this.result.set(null);
    this.loadError.set(null);

    if (source === 'template') {
      this.profile.template().subscribe({
        next: ({ text, claude_prompt }) => {
          this.text.set(text);
          this.prompt.set(claude_prompt);
          this.check();
        },
        error: () => this.loadError.set('Could not load the template. Try pasting instead.'),
      });
    } else {
      this.text.set('');
      this.fileName.set(null);
    }
  }

  onFile(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) {
      return;
    }
    if (file.size > MAX_BYTES) {
      this.loadError.set('That file is over 512 KB. A profile is plain text and should be tiny.');
      return;
    }
    file
      .text()
      .then((text) => {
        this.loadError.set(null);
        this.fileName.set(file.name);
        this.text.set(text);
        this.check();
      })
      .catch(() => this.loadError.set('Could not read that file.'));
  }

  update(text: string): void {
    this.text.set(text);
    // Stale results are worse than none, so drop them the moment the text moves.
    this.result.set(null);
  }

  check(): void {
    const text = this.text();
    if (!text.trim()) {
      return;
    }
    this.checking.set(true);
    this.profile.validate(text).subscribe({
      next: (result) => {
        this.result.set(result);
        this.checking.set(false);
      },
      error: () => {
        this.checking.set(false);
        this.loadError.set('Could not reach the validator.');
      },
    });
  }

  save(): void {
    if (!this.canSave()) {
      return;
    }
    this.saving.set(true);
    this.profile.save(this.text(), null).subscribe({
      next: () => {
        this.saving.set(false);
        this.toast.ok('Profile saved. You can edit it any time from the Profile tab.');
        this.router.navigate(['/generate']);
      },
      error: () => this.saving.set(false),
    });
  }

  openClaude(): void {
    openClaude(this.prompt());
    this.toast.ok('Paste what Claude gives you back over the file below.');
  }

  async copyPrompt(): Promise<void> {
    const ok = await copyPrompt(this.prompt());
    this.copied.set(ok);
    if (ok) {
      // A tick on the button says it better than a toast that covers the page.
      setTimeout(() => this.copied.set(false), 2000);
    } else {
      this.loadError.set('Could not reach the clipboard. Select the prompt and copy it by hand.');
    }
  }

  restart(): void {
    this.source.set(null);
    this.text.set('');
    this.result.set(null);
    this.fileName.set(null);
    this.loadError.set(null);
  }

  /** The offending line, so an error is readable without counting rows. */
  lineText(issue: ProfileIssue): string {
    return issue.line ? (this.lines()[issue.line - 1] ?? '').trim() : '';
  }
}
