import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, finalize, tap } from 'rxjs';

import { API } from './api';
import { ExportResponse, GenerateRequest, GenerateResponse, GeneratedCv } from './models';

/**
 * Holds the current draft. It lives in the service rather than the page so a
 * route change to /applications and back does not throw away a generation that
 * cost two model calls.
 */
@Injectable({ providedIn: 'root' })
export class GenerateService {
  private readonly http = inject(HttpClient);

  readonly result = signal<GenerateResponse | null>(null);
  readonly generating = signal(false);
  readonly exporting = signal(false);
  readonly lastRequest = signal<GenerateRequest | null>(null);

  generate(body: GenerateRequest): Observable<GenerateResponse> {
    this.generating.set(true);
    return this.http.post<GenerateResponse>(`${API}/api/generate`, body).pipe(
      tap((res) => {
        this.result.set(res);
        this.lastRequest.set(body);
      }),
      finalize(() => this.generating.set(false)),
    );
  }

  /** Re-rolls the summary only, so a good bullet selection is not thrown away. */
  regenerateSummary(titleVariant: string): Observable<{ summary: string }> {
    const jd = this.lastRequest()?.jd_text ?? '';
    return this.http
      .post<{ summary: string }>(`${API}/api/generate/summary`, {
        jd_text: jd,
        title_variant: titleVariant,
      })
      .pipe(
        tap(({ summary }) => {
          const current = this.result();
          if (current) {
            this.result.set({ ...current, cv: { ...current.cv, summary } });
          }
        }),
      );
  }

  export(cv: GeneratedCv): Observable<ExportResponse> {
    this.exporting.set(true);
    return this.http
      .post<ExportResponse>(`${API}/api/export`, { application_draft: cv })
      .pipe(finalize(() => this.exporting.set(false)));
  }

  clear(): void {
    this.result.set(null);
    this.lastRequest.set(null);
  }
}
