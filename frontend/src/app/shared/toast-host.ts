import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { ToastService } from '../core/toast.service';
import { Icon } from './icon';

@Component({
  selector: 'app-toast-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `
    <!-- polite, so a toast never steals focus mid-typing -->
    <div
      class="pointer-events-none fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2"
      aria-live="polite"
    >
      @for (toast of toasts.toasts(); track toast.id) {
        <div
          class="card pointer-events-auto flex items-start gap-2 p-3 shadow-lg"
          [class.border-danger]="toast.kind === 'error'"
        >
          <span [class]="toast.kind === 'error' ? 'text-danger' : 'text-accent'">
            <app-icon [name]="toast.kind === 'error' ? 'alert' : 'check'" />
          </span>
          <p class="flex-1 text-[13px] leading-snug">{{ toast.message }}</p>
          <button
            type="button"
            class="text-fg-subtle hover:text-fg cursor-pointer"
            (click)="toasts.dismiss(toast.id)"
            aria-label="Dismiss notification"
          >
            <app-icon name="x" [size]="14" />
          </button>
        </div>
      }
    </div>
  `,
})
export class ToastHost {
  readonly toasts = inject(ToastService);
}
