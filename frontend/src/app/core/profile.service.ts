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
      .pipe(tap(() => this.landed()));
  }

  /** One bullet's wording, edited in place. The rest of the file is untouched. */
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

  /**
   * Describe a change and get back a proposal. Saves nothing: the reply carries
   * the profile as it would be, and confirming is an ordinary save().
   */
  ask(message: string, history: AskTurn[], pending: AskChange[]): Observable<AskReply> {
    return this.http.post<AskReply>(`${API}/api/profile/ask`, { message, history, pending });
  }

  /** Every save appends one. Newest first, the first is current. */
  versions(): Observable<ProfileVersion[]> {
    return this.http.get<ProfileVersion[]>(`${API}/api/profile/versions`);
  }

  /** What restoring this version would change, read against the saved profile. */
  diff(version: number): Observable<ProfileDiff> {
    return this.http.get<ProfileDiff>(`${API}/api/profile/versions/${version}/diff`);
  }

  /**
   * Puts an old version back by appending it as a new one, so nothing is lost
   * and a restore can itself be undone. Goes through the same save path, which
   * is why it takes the same conflict token.
   */
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
