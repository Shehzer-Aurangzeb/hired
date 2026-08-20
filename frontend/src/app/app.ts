import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { Icon } from './shared/icon';
import { ToastHost } from './shared/toast-host';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon, ToastHost],
  templateUrl: './app.html',
})
export class App {
  readonly nav = [
    { path: '/generate', label: 'Generate', icon: 'sparkles' },
    { path: '/applications', label: 'Applications', icon: 'file-text' },
    { path: '/profile', label: 'Profile', icon: 'user' },
  ] as const;
}
