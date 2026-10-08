import { HttpClient, httpResource } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, of, shareReplay, tap } from 'rxjs';

import { API } from './api';
import { AuthService } from './auth.service';
import {
  AskChange,
  AskReply,
  AskTurn,
  Profile,
  ProfileDiff,
  ProfileSource,
  ProfileTemplate,
  ProfileVersion,
  ValidationResult,
} from './models';

@Injectable({ providedIn: 'root' })
export class ProfileService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  /** Null until the first check. */
  readonly exists = signal<boolean | null>(null);

  // Only fetches once signed in with a saved profile, so the lock screen never hits a 401.
  readonly profile = httpResource<Profile>(() =>
    this.auth.authenticated() && this.exists() ? `${API}/api/profile` : undefined,
  );

  private probe?: Observable<boolean>;

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

  /** The backend returns 409 if the profile changed since `expectedUpdatedAt`. */
  save(text: string, expectedUpdatedAt: string | null): Observable<ProfileSource> {
    return this.http
      .put<ProfileSource>(`${API}/api/profile/source`, {
        text,
        expected_updated_at: expectedUpdatedAt,
      })
      .pipe(tap(() => this.landed()));
  }

  saveBullet(
    id: string,
    text: string,
    expectedUpdatedAt: string | null,
  ): Observable<ProfileSource> {
    return this.http
      .patch<ProfileSource>(`${API}/api/profile/bullets/${encodeURIComponent(id)}`, {
        text,
        expected_updated_at: expectedUpdatedAt,
      })
      .pipe(tap(() => this.landed()));
  }

  /** Returns a proposed change. Saves nothing; confirming calls save(). */
  ask(message: string, history: AskTurn[], pending: AskChange[]): Observable<AskReply> {
    return this.http.post<AskReply>(`${API}/api/profile/ask`, { message, history, pending });
  }

  /** Newest first; the first is current. */
  versions(): Observable<ProfileVersion[]> {
    return this.http.get<ProfileVersion[]>(`${API}/api/profile/versions`);
  }

  diff(version: number): Observable<ProfileDiff> {
    return this.http.get<ProfileDiff>(`${API}/api/profile/versions/${version}/diff`);
  }

  /** Saves the old version as a new one, so a restore can be undone too. */
  restore(version: number, expectedUpdatedAt: string | null): Observable<ProfileSource> {
    return this.http
      .post<ProfileSource>(`${API}/api/profile/versions/${version}/restore`, {
        expected_updated_at: expectedUpdatedAt,
      })
      .pipe(tap(() => this.landed()));
  }

  private landed(): void {
    this.exists.set(true);
    this.probe = undefined;
    this.profile.reload();
  }
}
