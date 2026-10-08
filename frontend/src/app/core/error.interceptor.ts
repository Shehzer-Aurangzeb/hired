import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { ToastService } from './toast.service';

// Toast each failed call, then rethrow so the caller can still react.
// 401s are skipped: the login form and authInterceptor already handle them.
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
