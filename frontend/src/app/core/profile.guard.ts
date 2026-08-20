import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import { ProfileService } from './profile.service';

/** Nothing in the app works without a profile, so first run goes to setup. */
export const profileGuard: CanActivateFn = () => {
  const profile = inject(ProfileService);
  const router = inject(Router);

  return profile.ensure().pipe(map((ok) => ok || router.createUrlTree(['/setup'])));
};

/** Setup is only for the first run. With a profile saved it is a dead end. */
export const setupGuard: CanActivateFn = () => {
  const profile = inject(ProfileService);
  const router = inject(Router);

  return profile.ensure().pipe(map((ok) => !ok || router.createUrlTree(['/profile'])));
};
