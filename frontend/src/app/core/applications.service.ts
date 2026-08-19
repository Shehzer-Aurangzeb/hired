import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './api';
import { Application, ApplicationStatus } from './models';

@Injectable({ providedIn: 'root' })
export class ApplicationsService {
  private readonly http = inject(HttpClient);

  list(): Observable<Application[]> {
    return this.http.get<Application[]>(`${API}/api/applications`);
  }

  get(id: number): Observable<Application> {
    return this.http.get<Application>(`${API}/api/applications/${id}`);
  }

  updateStatus(id: number, status: ApplicationStatus): Observable<Application> {
    return this.http.patch<Application>(`${API}/api/applications/${id}`, { status });
  }

  pdfUrl(id: number): string {
    return `${API}/api/applications/${id}/pdf`;
  }
}
