import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import { AuthService } from './auth.service';

/** No session, no screens. Every route but /login goes through this. */
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return auth
    .ensure()
    .pipe(
      map(
        (ok) =>
          ok ||
          router.createUrlTree(['/login'], { queryParams: { next: state.url } }),
      ),
    );
};

/** Already in? Then /login is not a place you need to be. */
export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return auth.ensure().pipe(map((ok) => !ok || router.createUrlTree(['/generate'])));
};
