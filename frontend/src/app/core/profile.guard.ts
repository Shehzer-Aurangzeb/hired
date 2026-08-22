import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of, switchMap } from 'rxjs';

import { AuthService } from './auth.service';
import { ProfileService } from './profile.service';

/*
 * Both guards wait on the session before asking whether a profile exists.
 * Angular evaluates a route's canActivate guards concurrently, so neither can
 * assume authGuard already ran, and asking the API while signed out is a
 * guaranteed 401. Signed out they return true and let authGuard's redirect win.
 *
 * Everything is injected up front: inject() only works during construction, not
 * inside the switchMap callback that runs once the session check resolves.
 */

/** Nothing in the app works without a profile, so first run goes to setup. */
export const profileGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const profile = inject(ProfileService);
  const router = inject(Router);

  return auth.ensure().pipe(
    switchMap((signedIn) => (signedIn ? profile.ensure() : of(true))),
    map((ok) => ok || router.createUrlTree(['/setup'])),
  );
};

/** Setup is only for the first run. With a profile saved it is a dead end. */
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
