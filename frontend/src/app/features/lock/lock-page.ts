import { ChangeDetectionStrategy, Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { MOCK_PASSWORD, USE_MOCKS } from '../../core/api';
import { AuthService } from '../../core/auth.service';
import { Icon } from '../../shared/icon';

@Component({
  selector: 'app-lock-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, Icon],
  templateUrl: './lock-page.html',
})
export class LockPage {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private readonly field = viewChild<ElementRef<HTMLInputElement>>('password');

  readonly form = this.fb.nonNullable.group({
    password: ['', Validators.required],
  });

  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly lockedFor = signal(0);
  readonly reveal = signal(false);

  /** The demo needs something to type. Never shown once mocks are off. */
  readonly demoPassword = USE_MOCKS ? MOCK_PASSWORD : null;

  submit(): void {
    if (this.form.invalid || this.busy() || this.lockedFor()) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);

    this.auth.login(this.form.getRawValue().password).subscribe((result) => {
      this.busy.set(false);
      if (result.ok) {
        const next = this.route.snapshot.queryParamMap.get('next');
        this.router.navigateByUrl(next && next !== '/login' ? next : '/generate');
        return;
      }
      this.error.set(result.message ?? 'That password is not right.');
      this.form.reset();
      this.field()?.nativeElement.focus();
      if (result.retryAfter) {
        this.countdown(result.retryAfter);
      }
    });
  }

  /** ponytail: setInterval, not a timer library. One counter, one screen. */
  private countdown(seconds: number): void {
    this.lockedFor.set(seconds);
    const tick = setInterval(() => {
      this.lockedFor.update((n) => n - 1);
      if (this.lockedFor() <= 0) {
        clearInterval(tick);
        this.error.set(null);
      }
    }, 1000);
  }
}
