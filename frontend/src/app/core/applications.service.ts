import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './api';
import { Application } from './models';

@Injectable({ providedIn: 'root' })
export class ApplicationsService {
  private readonly http = inject(HttpClient);

  /**
   * Keep this posting. Independent of whether a CV was ever made for it: the
   * records worth the most are often the ones you did not apply to.
   */
  create(body: Partial<Application>): Observable<Application> {
    return this.http.post<Application>(`${API}/api/applications`, body);
  }

  list(): Observable<Application[]> {
    return this.http.get<Application[]>(`${API}/api/applications`);
  }

  get(id: number): Observable<Application> {
    return this.http.get<Application>(`${API}/api/applications/${id}`);
  }

  /** One patch rather than a method per field. Status and notes are the only two. */
  patch(id: number, changes: Partial<Application>): Observable<Application> {
    return this.http.patch<Application>(`${API}/api/applications/${id}`, changes);
  }

  /**
   * TEMPORARY, paired with POST /api/reexport. Rebuilds the PDF from what the
   * row already stores, for rows exported before a template fix. Delete this
   * and the button on the detail page together.
   */
  reexport(id: number): Observable<{ filename: string; page_count: number }> {
    return this.http.post<{ filename: string; page_count: number }>(`${API}/api/reexport`, {
      application_id: id,
    });
  }

  /** Takes the PDF with it. Ask before calling this. */
  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${API}/api/applications/${id}`);
  }

  pdfUrl(id: number): string {
    return `${API}/api/applications/${id}/pdf`;
  }
}
