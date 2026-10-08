import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of, switchMap } from 'rxjs';

import { AuthService } from './auth.service';
import { ProfileService } from './profile.service';

// Guards run concurrently, so these wait for the session first and return true
// when signed out, letting authGuard redirect. inject() must run before switchMap.

/** No profile yet, so send to setup. */
export const profileGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const profile = inject(ProfileService);
  const router = inject(Router);

  return auth.ensure().pipe(
    switchMap((signedIn) => (signedIn ? profile.ensure() : of(true))),
    map((ok) => ok || router.createUrlTree(['/setup'])),
  );
};

/** Setup is first-run only. */
export const setupGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const profile = inject(ProfileService);
  const router = inject(Router);

  return auth.ensure().pipe(
    switchMap((signedIn) =>
      signedIn
        ? profile.ensure().pipe(map((has) => !has || router.createUrlTree(['/profile'])))
        : of(true),
    ),
  );
};
