import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './api';
import { Application } from './models';

@Injectable({ providedIn: 'root' })
export class ApplicationsService {
  private readonly http = inject(HttpClient);

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

  pdfUrl(id: number): string {
    return `${API}/api/applications/${id}/pdf`;
  }
}
