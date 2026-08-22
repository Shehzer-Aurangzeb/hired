import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { ToastService } from './toast.service';

/**
 * One toast per failed call, then rethrow so the caller can still react.
 *
 * 401 is the exception: the login form shows a wrong password inline, and
 * authInterceptor answers an expired session by sending you to the lock screen.
 * A toast on top of either is the same news told twice.
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(ToastService);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401) {
        toast.error(describe(error, req.url));
      }
      return throwError(() => error);
    }),
  );
};

function describe(error: HttpErrorResponse, url: string): string {
  if (error.status === 0) {
    return `Cannot reach the backend. Is it running on port 8000?`;
  }
  if (error.status === 404) {
    return `Not found: ${new URL(url, location.origin).pathname}`;
  }
  const detail = error.error?.detail;
  return typeof detail === 'string' ? detail : `Request failed (${error.status}).`;
}
