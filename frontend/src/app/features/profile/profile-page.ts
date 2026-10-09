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
  AskChange,
  AskReply,
  AskTurn,
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

type Tab = 'browse' | 'ask' | 'edit' | 'history';

const TAB_IDS: Tab[] = ['browse', 'ask', 'edit', 'history'];

function asTab(value: string | null): Tab {
  return TAB_IDS.includes(value as Tab) ? (value as Tab) : 'browse';
}

/** An employer, or the standalone projects shaped like one so both render the same. */
type Group = Experience & { standalone: boolean };

/** A blocked bullet or an unverified claim. */
export interface Unresolved {
  project: string;
  kind: 'blocked' | 'unverified';
  id: string;
  text: string;
  reason: string;
}

/** Shared by the line-number gutter and the textarea. */
const LINE_HEIGHT = 19;

@Component({
  selector: 'app-profile-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, KeyValuePipe],
  templateUrl: './profile-page.html',
  // Closing the tab bypasses the router guard, so warn here too.
  host: { '(window:beforeunload)': 'onUnload($event)' },
})
export class ProfilePage {
  private readonly service = inject(ProfileService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private readonly editor = viewChild<ElementRef<HTMLTextAreaElement>>('editor');

  readonly resource = this.service.profile;

  // Every tab writes itself to the URL, so every tab has to be readable back.
  // Only 'edit' was, which made ?tab=ask and ?tab=history land on Browse.
  readonly tab = signal<Tab>(asTab(this.route.snapshot.queryParamMap.get('tab')));

  constructor() {
    // Load up front so the editor is never empty (saving that would wipe the profile).
    this.load();
    // Landing straight on History from a link has to fetch, not wait for a click.
    if (this.tab() === 'history') {
      this.loadVersions();
    }
  }

  // ---------- browse ----------

  readonly query = signal('');

  // ---------- inline bullet edit ----------

  readonly editingBullet = signal<string | null>(null);
  readonly bulletDraft = signal('');
  readonly bulletSaving = signal(false);

  startBullet(id: string, text: string): void {
    // With unsaved editor changes, the next Save there would undo this edit.
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

  /** Projects from both employers and the standalone list. */
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

  /** Blocked bullets and unverified notes, as one list. */
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

  readonly shown = computed(() => this.groups().reduce((n, g) => n + g.projects.length, 0));

  readonly hasAvailability = computed(() =>
    Object.values(this.resource.value()?.availability ?? {}).some(nonEmpty),
  );

  /** The numeric rules always have defaults, so only the text parts count. */
  readonly hasRules = computed(() => {
    const rules = this.resource.value()?.rules;
    return !!rules && [rules.banned_words, rules.banned_chars, rules.preferred_phrasing].some(nonEmpty);
  });

  hasBoundary = hasBoundary;

  readonly identityLinks = computed(() => {
    const identity = this.resource.value()?.identity;
    if (!identity) {
      return [];
    }
    return [
      { text: 'LinkedIn', icon: 'linkedin', brand: 'brand-linkedin', url: identity.linkedin },
      { text: 'GitHub', icon: 'github', brand: 'brand-github', url: identity.github },
      { text: 'Portfolio', icon: 'globe', brand: 'brand-web', url: identity.portfolio },
      ...identity.links.map((link) => ({
        text: link.label || link.url,
        icon: 'globe',
        brand: 'brand-web',
        url: link.url,
      })),
    ].filter((link) => !!link.url);
  });

  /** Adds https:// so "github.com/you" is not treated as a relative link. */
  href(url: string): string {
    return /^https?:\/\//i.test(url) ? url : `https://${url}`;
  }

  jump(id: string): void {
    document.getElementById(`project-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ---------- edit ----------

  readonly text = signal('');
  /** Last text the server confirmed; dirty is measured against it. */
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

  readonly TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'browse', label: 'Browse', icon: 'user' },
    { id: 'ask', label: 'Ask', icon: 'claude' },
    { id: 'edit', label: 'Source', icon: 'file-text' },
    { id: 'history', label: 'History', icon: 'history' },
  ];

  readonly menuOpen = signal(false);

  setTab(tab: Tab): void {
    this.menuOpen.set(false);
    if (tab === 'history' && !this.versions().length) {
      this.loadVersions();
    }
    this.tab.set(tab);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tab: tab === 'browse' ? null : tab },
      replaceUrl: true,
    });
  }

  /** Only call with no unsaved edits. */
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
        if (this.tab() === 'history') {
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

  /** Discard my edits and take the server version. */
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

  /** Keep my edits on top of the server version so the next save succeeds. */
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

  // ---------- ask ----------
  // The model only proposes. Confirming goes through the normal save.

  /**
   * Built from whatever profile is loaded, never written here: hard-coded
   * project names put real clients in a public repo, and the demo would be
   * advertising somebody else's.
   */
  readonly askExamples = computed(() => {
    const profile = this.resource.value();
    const names = [
      ...(profile?.experience ?? []).flatMap((e) => e.projects),
      ...(profile?.projects ?? []),
    ].map((project) => project.name);
    const row = profile?.skills?.[0]?.line ?? 'Frontend';
    return [
      names.length >= 2
        ? `I used Redux on ${names[0]} and ${names[1]}`
        : names.length === 1
          ? `I used Redux on ${names[0]}`
          : 'I used Redux, working level',
      `Add i18next to the ${row} skills row`,
    ];
  });

  /** The first example doubles as the input's placeholder. */
  readonly askPlaceholder = computed(() => this.askExamples()[0]);

  readonly draft = signal('');
  readonly turns = signal<AskTurn[]>([]);
  readonly pending = signal<AskReply | null>(null);
  readonly asking = signal(false);
  readonly askError = signal<string | null>(null);

  readonly canAsk = computed(() => !!this.draft().trim() && !this.asking());
  /** Confirming replaces the editor text, so wait for no unsaved edits. */
  readonly canConfirm = computed(
    () => !!this.pending()?.text && !this.dirty() && !this.saving() && !this.conflict(),
  );

  send(): void {
    if (!this.canAsk()) {
      return;
    }
    const message = this.draft().trim();
    this.asking.set(true);
    this.askError.set(null);
    this.service.ask(message, this.turns(), this.pending()?.changes ?? []).subscribe({
      next: (reply) => {
        this.asking.set(false);
        this.draft.set('');
        this.turns.update((turns) => [
          ...turns,
          { role: 'you' as const, text: message },
          { role: 'model' as const, text: reply.reply },
        ]);
        // A question-only reply has no proposal, so keep the current one.
        this.pending.set(reply.text ? reply : { ...reply, ...this.keptProposal(reply) });
      },
      error: (error) => {
        this.asking.set(false);
        this.askError.set(
          error?.error?.detail ?? 'Could not reach the model. Nothing was changed.',
        );
      },
    });
  }

  private keptProposal(reply: AskReply): Partial<AskReply> {
    const held = this.pending();
    return held?.text
      ? { text: held.text, diff: held.diff, added: held.added, removed: held.removed, changes: held.changes }
      : {};
  }

  discard(): void {
    this.turns.set([]);
    this.pending.set(null);
    this.draft.set('');
    this.askError.set(null);
  }

  confirm(): void {
    const proposed = this.pending()?.text;
    if (!proposed || !this.canConfirm()) {
      return;
    }
    this.saving.set(true);
    this.service.save(proposed, this.updatedAt()).subscribe({
      next: (source) => {
        this.saving.set(false);
        this.text.set(source.text);
        this.saved.set(source.text);
        this.updatedAt.set(source.updated_at);
        this.version.set(source.version);
        this.result.set(null);
        this.discard();
        this.toast.ok(`Saved as v${source.version}.`);
      },
      error: (error) => {
        this.saving.set(false);
        if (error.status === 409) {
          this.conflict.set({ text: error.error?.text ?? '', updated_at: error.error?.updated_at });
          this.askError.set('The profile moved on while you were talking. Reload and ask again.');
        } else {
          this.askError.set('Could not save that.');
        }
      },
    });
  }

  // ---------- history ----------
  // Viewing works mid-edit; only restore needs no unsaved edits.

  readonly versions = signal<ProfileVersion[]>([]);
  readonly picked = signal<number | null>(null);
  readonly diff = signal<ProfileDiff | null>(null);
  readonly historyBusy = signal(false);
  readonly historyError = signal<string | null>(null);
  readonly confirming = signal<number | null>(null);

  readonly canRestore = computed(() => !this.dirty() && !this.saving() && !this.conflict());

  readonly nextVersion = computed(() => (this.version() ?? 0) + 1);

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

  /** Same prompt as first-run setup, fetched on demand. */
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

  /** Downloads the current editor text. */
  export(): void {
    download(this.text());
  }

  /** Jumps from a Browse card to its spot in the source. */
  editProject(name: string): void {
    this.setTab('edit');
    // Wait for the textarea and source to load; give up if the heading is missing.
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
      // Line count times line height; fine because the font is monospace.
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

  // ---------- unsaved changes ----------

  onUnload(event: BeforeUnloadEvent): void {
    if (this.dirty()) {
      event.preventDefault();
    }
  }

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
