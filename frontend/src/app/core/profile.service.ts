import { HttpClient, httpResource } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, of, shareReplay, tap } from 'rxjs';

import { API } from './api';
import { AuthService } from './auth.service';
import { Profile, ProfileSource, ProfileTemplate, ValidationResult } from './models';

@Injectable({ providedIn: 'root' })
export class ProfileService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  /** Null until the first check. The guard and the shell share one call. */
  readonly exists = signal<boolean | null>(null);

  // ponytail: httpResource gives value/error/isLoading signals in one line. It is
  // experimental in v20; swap for toSignal + catchError if the API churns.
  //
  // The URL is conditional so the resource stays idle until there is something to
  // fetch and someone allowed to fetch it. Unconditional, it fired on the lock
  // screen, where the answer is a 401 once auth lands and a 404 before then.
  readonly profile = httpResource<Profile>(() =>
    this.auth.authenticated() && this.exists() ? `${API}/api/profile` : undefined,
  );

  private probe?: Observable<boolean>;

  /** Has a profile been saved yet. Answers the "first run" question. */
  ensure(): Observable<boolean> {
    if (this.exists() === true) {
      return of(true);
    }
    this.probe ??= this.source().pipe(
      map((source) => source.exists),
      catchError(() => of(false)),
      tap((ok) => this.exists.set(ok)),
      shareReplay(1),
    );
    return this.probe;
  }

  source(): Observable<ProfileSource> {
    return this.http.get<ProfileSource>(`${API}/api/profile/source`);
  }

  template(): Observable<ProfileTemplate> {
    return this.http.get<ProfileTemplate>(`${API}/api/profile/template`);
  }

  validate(text: string): Observable<ValidationResult> {
    return this.http.post<ValidationResult>(`${API}/api/profile/validate`, { text });
  }

  /**
   * `expectedUpdatedAt` guards against clobbering a change made elsewhere. The
   * backend rejects with 409 when the stored value has moved on.
   */
  save(text: string, expectedUpdatedAt: string | null): Observable<ProfileSource> {
    return this.http
      .put<ProfileSource>(`${API}/api/profile/source`, {
        text,
        expected_updated_at: expectedUpdatedAt,
      })
      .pipe(
        tap(() => {
          this.exists.set(true);
          this.probe = undefined;
          this.profile.reload();
        }),
      );
  }
}
