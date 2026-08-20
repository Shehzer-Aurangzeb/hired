import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, of, shareReplay, tap } from 'rxjs';

import { API } from './api';

export interface LoginResult {
  ok: boolean;
  /** Set when the server is rate limiting. Seconds until another attempt is allowed. */
  retryAfter?: number;
  message?: string;
}

/**
 * The session lives in an httpOnly cookie set by the backend. Nothing secret is
 * kept in the browser, so an XSS bug cannot lift it, and `withCredentials` is
 * what carries it. The only thing tracked here is whether we are in or out.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  readonly authenticated = signal(false);
  readonly checked = signal(false);

  private probe?: Observable<boolean>;

  /** Runs once per page load. The guard and the shell both wait on the same call. */
  ensure(): Observable<boolean> {
    if (this.authenticated()) {
      return of(true);
    }
    this.probe ??= this.http
      .get<{ authenticated: boolean }>(`${API}/api/auth/session`, { withCredentials: true })
      .pipe(
        map((res) => res.authenticated),
        catchError(() => of(false)),
        tap((ok) => {
          this.authenticated.set(ok);
          this.checked.set(true);
        }),
        shareReplay(1),
      );
    return this.probe;
  }

  login(password: string): Observable<LoginResult> {
    return this.http
      .post<{ authenticated: boolean }>(
        `${API}/api/auth/login`,
        { password },
        { withCredentials: true, observe: 'response' },
      )
      .pipe(
        tap(() => {
          this.authenticated.set(true);
          this.checked.set(true);
          this.probe = undefined;
        }),
        map(() => ({ ok: true }) as LoginResult),
        catchError((error) => {
          if (error.status === 429) {
            const retryAfter = Number(error.error?.retry_after ?? 30);
            return of({ ok: false, retryAfter, message: error.error?.detail } as LoginResult);
          }
          if (error.status === 401) {
            return of({ ok: false, message: 'That password is not right.' } as LoginResult);
          }
          if (error.status === 0) {
            return of({
              ok: false,
              message:
                'Cannot reach the server. If it has been idle it may be waking up, which can take half a minute.',
            } as LoginResult);
          }
          return of({ ok: false, message: 'Something went wrong signing in.' } as LoginResult);
        }),
      );
  }

  logout(): Observable<unknown> {
    this.clear();
    return this.http
      .post(`${API}/api/auth/logout`, {}, { withCredentials: true })
      .pipe(catchError(() => of(null)));
  }

  /** Called by the interceptor when anything comes back 401. */
  clear(): void {
    this.authenticated.set(false);
    this.probe = undefined;
  }
}
