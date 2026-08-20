import { HttpClient, httpResource } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, of, shareReplay, tap } from 'rxjs';

import { API } from './api';
import { Profile, ProfileSource, ValidationResult } from './models';

@Injectable({ providedIn: 'root' })
export class ProfileService {
  private readonly http = inject(HttpClient);

  // ponytail: httpResource gives value/error/isLoading signals in one line. It is
  // experimental in v20; swap for toSignal + catchError if the API churns.
  readonly profile = httpResource<Profile>(() => `${API}/api/profile`);

  /** Null until the first check. The guard and the shell share one call. */
  readonly exists = signal<boolean | null>(null);

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

  template(): Observable<string> {
    return this.http
      .get<{ text: string }>(`${API}/api/profile/template`)
      .pipe(map((res) => res.text));
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
