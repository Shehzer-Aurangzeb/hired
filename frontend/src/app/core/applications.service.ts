import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './api';
import { Application, Artifact } from './models';

@Injectable({ providedIn: 'root' })
export class ApplicationsService {
  private readonly http = inject(HttpClient);

  /** Saves a posting, whether or not a CV was made for it. */
  create(body: Partial<Application>): Observable<Application> {
    return this.http.post<Application>(`${API}/api/applications`, body);
  }

  list(): Observable<Application[]> {
    return this.http.get<Application[]>(`${API}/api/applications`);
  }

  get(id: number): Observable<Application> {
    return this.http.get<Application>(`${API}/api/applications/${id}`);
  }

  patch(id: number, changes: Partial<Application>): Observable<Application> {
    return this.http.patch<Application>(`${API}/api/applications/${id}`, changes);
  }

  /** Writes an email or a form answer from the application and keeps it on the row. */
  writeArtifact(
    id: number,
    body: { kind: 'email' | 'answer'; question?: string; model?: string },
  ): Observable<Artifact> {
    return this.http.post<Artifact>(`${API}/api/applications/${id}/artifacts`, body);
  }

  /** Temporary: rebuilds the stored PDF. Remove with POST /api/reexport and its button. */
  reexport(id: number): Observable<{ filename: string; page_count: number; dropped: string[] }> {
    return this.http.post<{ filename: string; page_count: number; dropped: string[] }>(
      `${API}/api/reexport`,
      { application_id: id },
    );
  }

  /** Also deletes the PDF. Confirm before calling. */
  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${API}/api/applications/${id}`);
  }

  pdfUrl(id: number): string {
    return `${API}/api/applications/${id}/pdf`;
  }
}
