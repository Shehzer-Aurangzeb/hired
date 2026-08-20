import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from './core/auth.service';
import { ProfileService } from './core/profile.service';
import { Icon } from './shared/icon';
import { ToastHost } from './shared/toast-host';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon, ToastHost],
  templateUrl: './app.html',
})
export class App {
  readonly auth = inject(AuthService);
  readonly profile = inject(ProfileService);
  private readonly router = inject(Router);

  signOut(): void {
    this.auth.logout().subscribe(() => this.router.navigate(['/login']));
  }

  readonly nav = [
    { path: '/generate', label: 'Generate', icon: 'sparkles' },
    { path: '/applications', label: 'Applications', icon: 'file-text' },
    { path: '/profile', label: 'Profile', icon: 'user' },
  ] as const;
}
