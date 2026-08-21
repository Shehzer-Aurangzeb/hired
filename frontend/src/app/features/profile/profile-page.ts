import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { ActivatedRoute, CanDeactivateFn, Router } from '@angular/router';

import { MAX_BYTES, USE_MOCKS } from '../../core/api';
import { openClaude } from '../../core/claude-draft';
import { ago } from '../../core/dates';
import { Bullet, Project, ProfileIssue, ValidationResult } from '../../core/models';
import { ProfileService } from '../../core/profile.service';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

type Tab = 'browse' | 'edit';

/** The gutter and the textarea must agree, so the number is in one place. */
const LINE_HEIGHT = 19;

/**
 * Two jobs, two tabs. Browse is the parsed profile, which is how you check that
 * a hand edit landed the way you meant. Edit is the raw markdown, which is the
 * only thing that is actually stored. The file is the format, so there is no
 * form-based editor to keep in sync with it.
 */
@Component({
  selector: 'app-profile-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  templateUrl: './profile-page.html',
  // Closing the tab bypasses the router, so the browser gets its own warning.
  host: { '(window:beforeunload)': 'onUnload($event)' },
})
export class ProfilePage {
  private readonly service = inject(ProfileService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private readonly editor = viewChild<ElementRef<HTMLTextAreaElement>>('editor');

  readonly resource = this.service.profile;
  readonly mocked = USE_MOCKS;

  readonly tab = signal<Tab>(
    this.route.snapshot.queryParamMap.get('tab') === 'edit' ? 'edit' : 'browse',
  );

  constructor() {
    // Up front, not on first sight of the Edit tab. The header says when the
    // profile was last saved and that has to be true on both tabs, and an editor
    // that renders empty is one Save away from wiping the real profile.
    this.load();
  }

  // ---------- browse ----------

  readonly query = signal('');

  private readonly projects = computed<Project[]>(() =>
    (this.resource.value()?.experience ?? []).flatMap((e) => e.projects),
  );

  private readonly bullets = computed<Bullet[]>(() =>
    this.projects().flatMap((p) => p.bullets),
  );

  readonly health = computed(() => ({
    projects: this.projects().length,
    bullets: this.bullets().length,
    blocked: this.bullets().filter((b) => b.status === 'blocked').length,
    missing: this.projects().filter((p) => !hasBoundary(p)).length,
  }));

  readonly experience = computed(() => {
    const query = this.query().trim().toLowerCase();
    if (!query) {
      return this.resource.value()?.experience ?? [];
    }
    return (this.resource.value()?.experience ?? [])
      .map((company) => ({
        ...company,
        projects: company.projects.filter(
          (project) =>
            project.name.toLowerCase().includes(query) ||
            project.tags.some((t) => t.includes(query)) ||
            project.stack.some((s) => s.toLowerCase().includes(query)) ||
            project.bullets.some((b) => b.text.toLowerCase().includes(query)),
        ),
      }))
      .filter((company) => company.projects.length > 0);
  });

  /** "3 of 12" — a filter that hides things has to say how many. */
  readonly shown = computed(() => this.experience().reduce((n, c) => n + c.projects.length, 0));

  hasBoundary = hasBoundary;

  /** Profiles are written "github.com/you", which a bare href reads as relative. */
  href(url: string): string {
    return /^https?:\/\//i.test(url) ? url : `https://${url}`;
  }

  jump(id: string): void {
    document.getElementById(`project-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ---------- edit ----------

  readonly text = signal('');
  /** Last text the server confirmed. Everything dirty is measured against it. */
  readonly saved = signal('');
  readonly updatedAt = signal<string | null>(null);
  readonly result = signal<ValidationResult | null>(null);
  readonly loading = signal(false);
  readonly checking = signal(false);
  readonly saving = signal(false);
  readonly editError = signal<string | null>(null);
  readonly conflict = signal<{ text: string; updated_at: string | null } | null>(null);

  readonly dirty = computed(() => this.text() !== this.saved());
  readonly lines = computed(() => this.text().split('\n'));
  readonly lineNumbers = computed(() => this.lines().map((_, i) => i + 1));
  readonly errorLines = computed(
    () => new Set((this.result()?.errors ?? []).map((e) => e.line).filter(Boolean)),
  );
  readonly canSave = computed(
    () => !!this.result()?.ok && this.dirty() && !this.saving() && !this.conflict(),
  );

  readonly updatedLabel = computed(() => ago(this.updatedAt()));

  setTab(tab: Tab): void {
    this.tab.set(tab);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tab: tab === 'browse' ? null : tab },
      replaceUrl: true,
    });
  }

  /** Re-reading would throw away edits, so this only ever runs on a clean buffer. */
  load(): void {
    if (this.loading() || this.dirty()) {
      return;
    }
    this.loading.set(true);
    this.editError.set(null);
    this.service.source().subscribe({
      next: (source) => {
        this.text.set(source.text);
        this.saved.set(source.text);
        this.updatedAt.set(source.updated_at);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.editError.set('Could not load the saved profile.');
      },
    });
  }

  update(text: string): void {
    this.text.set(text);
    // A stale green tick is worse than no tick.
    this.result.set(null);
  }

  check(): void {
    if (!this.text().trim()) {
      return;
    }
    this.checking.set(true);
    this.service.validate(this.text()).subscribe({
      next: (result) => {
        this.result.set(result);
        this.checking.set(false);
      },
      error: () => {
        this.checking.set(false);
        this.editError.set('Could not reach the validator.');
      },
    });
  }

  save(): void {
    if (!this.canSave()) {
      return;
    }
    this.saving.set(true);
    this.editError.set(null);
    this.service.save(this.text(), this.updatedAt()).subscribe({
      next: (source) => {
        this.saving.set(false);
        this.saved.set(source.text);
        this.updatedAt.set(source.updated_at);
        this.toast.ok('Profile saved.');
      },
      error: (error) => {
        this.saving.set(false);
        if (error.status === 409) {
          this.conflict.set({ text: error.error?.text ?? '', updated_at: error.error?.updated_at });
        }
      },
    });
  }

  /** Throw away my edits and take what is on the server. */
  takeTheirs(): void {
    const theirs = this.conflict();
    if (!theirs) {
      return;
    }
    this.text.set(theirs.text);
    this.saved.set(theirs.text);
    this.updatedAt.set(theirs.updated_at);
    this.result.set(null);
    this.conflict.set(null);
  }

  /** Keep my edits and rebase onto their version, so the next save goes through. */
  keepMine(): void {
    const theirs = this.conflict();
    if (theirs) {
      this.updatedAt.set(theirs.updated_at);
    }
    this.conflict.set(null);
  }

  revert(): void {
    this.text.set(this.saved());
    this.result.set(null);
  }

  onFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    if (file.size > MAX_BYTES) {
      this.editError.set('That file is over 512 KB. A profile is plain text and should be tiny.');
      return;
    }
    file
      .text()
      .then((text) => {
        this.editError.set(null);
        this.update(text);
        this.setTab('edit');
        this.toast.ok(`Loaded ${file.name}. Nothing is saved until you check it and press Save.`);
      })
      .catch(() => this.editError.set('Could not read that file.'));
  }

  /** Same briefing as first-run setup, for a rewrite rather than a first draft. */
  draftWithClaude(): void {
    this.service.template().subscribe({
      next: (template) => {
        openClaude(template);
        this.toast.ok('Prompt copied. Paste Claude\'s answer over the source here.');
      },
      error: () => this.editError.set('Could not load the template.'),
    });
  }

  /** A local copy before you break something. Exports the buffer on screen. */
  export(): void {
    download(this.text());
  }

  /** Browse card to the exact spot in the source that produced it. */
  editProject(name: string): void {
    this.setTab('edit');
    // The textarea does not exist until the tab renders and the source lands,
    // so this waits on loading() rather than on a frame count. A heading that is
    // genuinely absent stops the wait instead of spinning it out.
    let tries = 0;
    const attempt = () => {
      const area = this.editor()?.nativeElement;
      if (!area || this.loading()) {
        if (tries++ < 300) {
          requestAnimationFrame(attempt);
        }
        return;
      }
      const at = this.text().indexOf(`### ${name}`);
      if (at < 0) {
        return;
      }
      area.focus();
      area.setSelectionRange(at, at);
      // ponytail: line height times line count. Exact enough because the font is
      // monospace and the box does not wrap headings.
      area.scrollTop = this.text().slice(0, at).split('\n').length * LINE_HEIGHT - LINE_HEIGHT * 2;
    };
    requestAnimationFrame(attempt);
  }

  lineText(issue: ProfileIssue): string {
    return issue.line ? (this.lines()[issue.line - 1] ?? '').trim() : '';
  }

  reload(): void {
    this.resource.reload();
  }

  // ---------- leaving with unsaved work ----------

  onUnload(event: BeforeUnloadEvent): void {
    if (this.dirty()) {
      event.preventDefault();
    }
  }

  /** ponytail: native confirm. A styled modal for one prompt is not worth owning. */
  confirmLeave(): boolean {
    return (
      !this.dirty() ||
      confirm('You have unsaved changes to your profile. Leave the page and lose them?')
    );
  }
}

export const profileLeaveGuard: CanDeactivateFn<ProfilePage> = (page) => page.confirmLeave();

function hasBoundary(project: Project): boolean {
  const b = project.claim_boundary;
  return !!(b.can_claim.length || b.cannot_claim.length || b.required_qualifiers.length);
}

function download(text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'master.md';
  link.click();
  URL.revokeObjectURL(url);
}
