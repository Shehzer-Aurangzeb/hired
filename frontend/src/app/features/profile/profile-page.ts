import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { KeyValuePipe } from '@angular/common';
import { ActivatedRoute, CanDeactivateFn, Router } from '@angular/router';

import { MAX_BYTES } from '../../core/api';
import { copyPrompt, openClaude } from '../../core/claude-draft';
import { ago } from '../../core/dates';
import {
  Bullet,
  Experience,
  Project,
  ProfileDiff,
  ProfileIssue,
  ProfileVersion,
  ValidationResult,
} from '../../core/models';
import { ProfileService } from '../../core/profile.service';
import { ToastService } from '../../core/toast.service';
import { Icon } from '../../shared/icon';

type Tab = 'browse' | 'edit';

/**
 * An employer, or the standalone Projects section wearing the same shape. The
 * two are separate lists in the model on purpose, but they render identically,
 * and one group type beats a second copy of the project card markup.
 */
type Group = Experience & { standalone: boolean };

/** One thing waiting on you: a blocked bullet, or something you cannot evidence. */
export interface Unresolved {
  project: string;
  kind: 'blocked' | 'unverified';
  id: string;
  text: string;
  reason: string;
}

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
  imports: [Icon, KeyValuePipe],
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

  // ---------- editing one bullet in place ----------

  readonly editingBullet = signal<string | null>(null);
  readonly bulletDraft = signal('');
  readonly bulletSaving = signal(false);

  startBullet(id: string, text: string): void {
    // The source editor holds the whole file. Letting a bullet edit land while
    // that buffer is dirty means the next Save there silently reverts it.
    if (this.dirty()) {
      this.toast.error('Save or revert your source edits first.');
      return;
    }
    this.editingBullet.set(id);
    this.bulletDraft.set(text);
  }

  cancelBullet(): void {
    this.editingBullet.set(null);
    this.bulletDraft.set('');
  }

  saveBullet(): void {
    const id = this.editingBullet();
    const text = this.bulletDraft().trim();
    if (!id || !text || this.bulletSaving()) {
      return;
    }
    this.bulletSaving.set(true);
    this.service.saveBullet(id, text, this.updatedAt()).subscribe({
      next: (source) => {
        // The editor buffer is the same document, so it moves with it.
        this.text.set(source.text);
        this.saved.set(source.text);
        this.updatedAt.set(source.updated_at);
        this.bulletSaving.set(false);
        this.cancelBullet();
        this.toast.ok('Bullet saved.');
      },
      error: () => this.bulletSaving.set(false),
    });
  }

  /** Employment is not what makes something a project, so both lists count. */
  private readonly projects = computed<Project[]>(() => {
    const profile = this.resource.value();
    return profile ? [...profile.experience.flatMap((e) => e.projects), ...profile.projects] : [];
  });

  private readonly bullets = computed<Bullet[]>(() =>
    this.projects().flatMap((p) => p.bullets),
  );

  readonly health = computed(() => ({
    projects: this.projects().length,
    bullets: this.bullets().length,
    missing: this.projects().filter((p) => !hasBoundary(p)).length,
  }));

  /**
   * Blocked bullets and unverified notes are one queue, not two lists. They are
   * the same job — go and check something — and splitting them means the shorter
   * half never gets looked at.
   */
  readonly unresolved = computed<Unresolved[]>(() =>
    this.projects().flatMap((project) => [
      ...project.unverified.map((text) => ({
        project: project.name,
        kind: 'unverified' as const,
        id: '',
        text,
        reason: '',
      })),
      ...project.bullets
        .filter((bullet) => bullet.status === 'blocked')
        .map((bullet) => ({
          project: project.name,
          kind: 'blocked' as const,
          id: bullet.id,
          text: bullet.text,
          reason: bullet.blocked_reason,
        })),
    ]),
  );

  private readonly all = computed<Group[]>(() => {
    const profile = this.resource.value();
    if (!profile) {
      return [];
    }
    const employers = profile.experience.map((e) => ({ ...e, standalone: false }));
    if (!profile.projects.length) {
      return employers;
    }
    // A display grouping, not an employer: the header prints no role or dates
    // because there are none, rather than because they are missing.
    return [
      ...employers,
      {
        name: 'Standalone projects',
        role: '',
        start: '',
        end: '',
        location: '',
        employment_type: '',
        context: '',
        disclosure: '',
        previous_roles: [],
        priority: 3,
        projects: profile.projects,
        standalone: true,
      },
    ];
  });

  readonly groups = computed<Group[]>(() => {
    const query = this.query().trim().toLowerCase();
    if (!query) {
      return this.all();
    }
    return this.all()
      .map((group) => ({
        ...group,
        projects: group.projects.filter(
          (project) =>
            project.name.toLowerCase().includes(query) ||
            project.tags.some((t) => t.includes(query)) ||
            project.stack.some((s) => s.toLowerCase().includes(query)) ||
            project.bullets.some((b) => b.text.toLowerCase().includes(query)),
        ),
      }))
      .filter((group) => group.projects.length > 0);
  });

  /** "3 of 12" — a filter that hides things has to say how many. */
  readonly shown = computed(() => this.groups().reduce((n, g) => n + g.projects.length, 0));

  /** Availability is all optional, so "did they write any of it" needs asking. */
  readonly hasAvailability = computed(() =>
    Object.values(this.resource.value()?.availability ?? {}).some(nonEmpty),
  );

  /** The three numbers always have defaults, so only the written parts count. */
  readonly hasRules = computed(() => {
    const rules = this.resource.value()?.rules;
    return !!rules && [rules.banned_words, rules.banned_chars, rules.preferred_phrasing].some(nonEmpty);
  });

  hasBoundary = hasBoundary;

  /** The named fields and the free-form list, as one row of anchors. */
  readonly identityLinks = computed(() => {
    const identity = this.resource.value()?.identity;
    if (!identity) {
      return [];
    }
    return [
      { text: identity.linkedin, url: identity.linkedin },
      { text: identity.github, url: identity.github },
      { text: identity.portfolio, url: identity.portfolio },
      // The label is what the line is for; the URL behind it is rarely readable.
      ...identity.links.map((link) => ({ text: link.label || link.url, url: link.url })),
    ].filter((link) => !!link.url);
  });

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
  readonly version = signal<number | null>(null);
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
        this.version.set(source.version);
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
        this.version.set(source.version);
        this.toast.ok('Profile saved.');
        if (this.historyOpen()) {
          this.loadVersions();
        }
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

  // ---------- history ----------
  //
  // Viewing is allowed mid-edit on purpose. "I have just broken something, what
  // did it look like before" is the main reason to open this, and a broken file
  // cannot be saved, so gating the whole drawer on a clean buffer would lock the
  // door at the moment it is wanted. Restore is what writes, so restore is what
  // waits for clean.

  readonly historyOpen = signal(false);
  readonly versions = signal<ProfileVersion[]>([]);
  readonly picked = signal<number | null>(null);
  readonly diff = signal<ProfileDiff | null>(null);
  readonly historyBusy = signal(false);
  readonly historyError = signal<string | null>(null);
  readonly confirming = signal<number | null>(null);

  /** The restore button needs a clean buffer: it replaces what is in the editor. */
  readonly canRestore = computed(() => !this.dirty() && !this.saving() && !this.conflict());

  /** What the next version will be called, for the confirmation copy. */
  readonly nextVersion = computed(() => (this.version() ?? 0) + 1);

  toggleHistory(): void {
    const open = !this.historyOpen();
    this.historyOpen.set(open);
    if (open) {
      this.loadVersions();
    } else {
      this.picked.set(null);
      this.diff.set(null);
      this.confirming.set(null);
    }
  }

  loadVersions(): void {
    this.historyBusy.set(true);
    this.historyError.set(null);
    this.service.versions().subscribe({
      next: (versions) => {
        this.versions.set(versions);
        this.historyBusy.set(false);
      },
      error: () => {
        this.historyBusy.set(false);
        this.historyError.set('Could not load the history.');
      },
    });
  }

  pick(version: number): void {
    this.confirming.set(null);
    if (this.picked() === version) {
      this.picked.set(null);
      this.diff.set(null);
      return;
    }
    this.picked.set(version);
    this.diff.set(null);
    this.historyBusy.set(true);
    this.service.diff(version).subscribe({
      next: (diff) => {
        this.diff.set(diff);
        this.historyBusy.set(false);
      },
      error: () => {
        this.historyBusy.set(false);
        this.historyError.set('Could not compare that version. It may have been pruned.');
      },
    });
  }

  restore(version: number): void {
    if (!this.canRestore()) {
      return;
    }
    this.historyBusy.set(true);
    this.service.restore(version, this.updatedAt()).subscribe({
      next: (source) => {
        this.historyBusy.set(false);
        this.confirming.set(null);
        this.picked.set(null);
        this.diff.set(null);
        this.text.set(source.text);
        this.saved.set(source.text);
        this.updatedAt.set(source.updated_at);
        this.version.set(source.version);
        this.result.set(null);
        this.loadVersions();
        this.toast.ok(`Restored v${version} as v${source.version}.`);
      },
      error: (error) => {
        this.historyBusy.set(false);
        this.confirming.set(null);
        if (error.status === 409) {
          this.conflict.set({ text: error.error?.text ?? '', updated_at: error.error?.updated_at });
          this.historyError.set('The profile moved on while this drawer was open.');
        } else {
          this.historyError.set('Could not restore that version.');
        }
      },
    });
  }

  since(when: string): string {
    return ago(when);
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

  readonly copied = signal(false);

  /**
   * Same briefing as first-run setup, for a rewrite rather than a first draft.
   * Fetched on use: the prompt is backend config and this is not the hot path.
   */
  draftWithClaude(open: boolean): void {
    this.service.template().subscribe({
      next: async ({ claude_prompt }) => {
        if (open) {
          const opened = await openClaude(claude_prompt);
          if (opened) {
            this.toast.ok('Prompt copied. Paste it as your first message in the tab that opened.');
          } else {
            this.editError.set('The tab is open but the clipboard refused. Copy it by hand.');
          }
          return;
        }
        const ok = await copyPrompt(claude_prompt);
        this.copied.set(ok);
        if (ok) {
          setTimeout(() => this.copied.set(false), 2000);
        } else {
          this.editError.set('Could not reach the clipboard.');
        }
      },
      error: () => this.editError.set('Could not load the Claude prompt.'),
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

function nonEmpty(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (value && typeof value === 'object') {
    return Object.keys(value).length > 0;
  }
  return !!value;
}
