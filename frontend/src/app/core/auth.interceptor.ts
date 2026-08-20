import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthService } from './auth.service';

/**
 * A 401 from anywhere means the session went away, so drop it and send the
 * person to the lock screen. Login itself is skipped: a wrong password there is
 * handled in the form, not by a redirect.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const isAuthCall = req.url.includes('/api/auth/');

  return next(req.clone({ withCredentials: true })).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !isAuthCall) {
        auth.clear();
        router.navigate(['/login'], { queryParams: { next: router.url } });
      }
      return throwError(() => error);
    }),
  );
};
