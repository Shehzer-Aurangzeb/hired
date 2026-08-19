import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { Bullet } from '../../core/models';
import { ProfileService } from '../../core/profile.service';
import { Icon } from '../../shared/icon';

/**
 * Read-only view of the parsed master.md. This is how you check that a hand edit
 * parsed the way you meant it to, before anything downstream selects from it.
 */
@Component({
  selector: 'app-profile-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  templateUrl: './profile-page.html',
})
export class ProfilePage {
  readonly resource = inject(ProfileService).profile;
  readonly query = signal('');

  private readonly bullets = computed<Bullet[]>(() =>
    (this.resource.value()?.experience ?? [])
      .flatMap((e) => e.projects)
      .flatMap((p) => p.bullets),
  );

  readonly total = computed(() => this.bullets().length);
  readonly blocked = computed(() => this.bullets().filter((b) => b.status === 'blocked').length);

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

  reload(): void {
    this.resource.reload();
  }
}
