import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, finalize, tap } from 'rxjs';

import { API } from './api';
import { ToastService } from './toast.service';
import {
  ExportResponse,
  FitResponse,
  GenerateRequest,
  GenerateResponse,
  GeneratedCv,
} from './models';

// Holds the current draft here, not in the page, so it survives navigating away.
@Injectable({ providedIn: 'root' })
export class GenerateService {
  private readonly http = inject(HttpClient);
  private readonly toast = inject(ToastService);

  readonly fit = signal<FitResponse | null>(null);
  readonly result = signal<GenerateResponse | null>(null);
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
        this.result.set(null);
        this.applicationId.set(null);
        this.say(res.notice);
      }),
      finalize(() => this.checking.set(false)),
    );
  }

  generate(body: GenerateRequest): Observable<GenerateResponse> {
    this.generating.set(true);
    return this.http.post<GenerateResponse>(`${API}/api/generate`, body).pipe(
      tap((res) => {
        this.result.set(res);
        this.say(res.notice);
      }),
      finalize(() => this.generating.set(false)),
    );
  }

  /** A silent retry looks like a slow call, so the screen says it happened. */
  private say(notice: string | undefined): void {
    if (notice) {
      this.toast.error(notice);
    }
  }

  /** Swaps in another hand-written title and summary. No model call. */
  useVariant(title: string, summary: string): void {
    const current = this.result();
    if (current) {
      this.result.set({ ...current, cv: { ...current.cv, title, summary } });
    }
  }

  /** HTML from the PDF renderer, for the preview. */
  preview(cv: GeneratedCv): Observable<string> {
    return this.http.post(`${API}/api/preview`, { cv }, { responseType: 'text' });
  }

  export(applicationId: number, cv: GeneratedCv): Observable<ExportResponse> {
    this.exporting.set(true);
    return this.http
      .post<ExportResponse>(`${API}/api/export`, {
        application_id: applicationId,
        cv,
        // Stamped on the row, so the saved PDF records what chose its bullets.
        model: this.result()?.model ?? '',
      })
      .pipe(finalize(() => this.exporting.set(false)));
  }

  clear(): void {
    this.fit.set(null);
    this.result.set(null);
    this.applicationId.set(null);
    this.jdText.set('');
  }
}
