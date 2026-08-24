import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, finalize, tap } from 'rxjs';

import { API } from './api';
import {
  ExportResponse,
  FitResponse,
  GenerateRequest,
  GenerateResponse,
  GeneratedCv,
} from './models';

/**
 * Holds the current draft. It lives in the service rather than the page so a
 * route change to /applications and back does not throw away a generation that
 * cost two model calls.
 */
@Injectable({ providedIn: 'root' })
export class GenerateService {
  private readonly http = inject(HttpClient);

  /** What the posting is, and whether it is worth an evening. Nothing is saved. */
  readonly fit = signal<FitResponse | null>(null);
  /** The CV, once one has been asked for. Null while the fit is all there is. */
  readonly result = signal<GenerateResponse | null>(null);
  /** The saved row, once one exists. Export attaches its PDF to this. */
  readonly applicationId = signal<number | null>(null);
  readonly jdText = signal('');

  readonly checking = signal(false);
  readonly generating = signal(false);
  readonly exporting = signal(false);
  readonly saving = signal(false);

  checkFit(jdText: string): Observable<FitResponse> {
    this.checking.set(true);
    return this.http.post<FitResponse>(`${API}/api/fit`, { jd_text: jdText }).pipe(
      tap((res) => {
        this.fit.set(res);
        this.jdText.set(jdText);
        // A new posting is a new decision, so nothing from the last one carries.
        this.result.set(null);
        this.applicationId.set(null);
      }),
      finalize(() => this.checking.set(false)),
    );
  }

  generate(body: GenerateRequest): Observable<GenerateResponse> {
    this.generating.set(true);
    return this.http.post<GenerateResponse>(`${API}/api/generate`, body).pipe(
      tap((res) => this.result.set(res)),
      finalize(() => this.generating.set(false)),
    );
  }

  /**
   * Swap the headline and its paragraph for another pair you already wrote.
   *
   * Not a regeneration. Summaries are hand-written per framing in master.md, so
   * asking a model to re-roll one means prose on your CV that you never wrote,
   * which is the single thing this whole app is built not to do. Local, free,
   * and it leaves the bullet selection alone.
   */
  useVariant(title: string, summary: string): void {
    const current = this.result();
    if (current) {
      this.result.set({ ...current, cv: { ...current.cv, title, summary } });
    }
  }

  export(applicationId: number, cv: GeneratedCv): Observable<ExportResponse> {
    this.exporting.set(true);
    return this.http
      .post<ExportResponse>(`${API}/api/export`, { application_id: applicationId, cv })
      .pipe(finalize(() => this.exporting.set(false)));
  }

  clear(): void {
    this.fit.set(null);
    this.result.set(null);
    this.applicationId.set(null);
    this.jdText.set('');
  }
}
