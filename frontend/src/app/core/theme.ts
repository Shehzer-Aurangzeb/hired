import { Injectable, effect, signal } from '@angular/core';

type Mode = 'light' | 'dark';

@Injectable({ providedIn: 'root' })
export class Theme {
  readonly mode = signal<Mode>(initial());

  constructor() {
    // effect, not a method call in toggle(), so the DOM and localStorage stay in
    // step with the signal no matter who changes it.
    effect(() => {
      const mode = this.mode();
      document.documentElement.classList.toggle('dark', mode === 'dark');
      localStorage.setItem('hired-theme', mode);
    });
  }

  toggle(): void {
    this.mode.update((m) => (m === 'dark' ? 'light' : 'dark'));
  }
}

function initial(): Mode {
  const saved = localStorage.getItem('hired-theme');
  if (saved === 'light' || saved === 'dark') {
    return saved;
  }
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
