import { HttpErrorResponse, HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { Observable, delay, of, throwError } from 'rxjs';

import { USE_MOCKS } from './api';
import { Application, ApplicationStatus } from './models';
import { MOCK_APPLICATIONS, MOCK_GENERATE } from './mock-data';

// ponytail: module-level array, not a service. Mock state lives exactly as long
// as the tab does, which is the point. Delete this file when the backend lands.
let applications: Application[] = MOCK_APPLICATIONS.map((a) => ({ ...a }));

/**
 * Answers the routes that have no backend yet (Phases 5, 6 and 9).
 * GET /api/profile is real and always falls through.
 */
export const mockInterceptor: HttpInterceptorFn = (req, next) => {
  if (!USE_MOCKS) {
    return next(req);
  }

  const path = new URL(req.url, location.origin).pathname;
  const handled = route(req.method, path, req.body);

  return handled ? handled : next(req);
};

function route(method: string, path: string, body: unknown): Observable<HttpResponse<unknown>> | null {
  const idMatch = /^\/api\/applications\/(\d+)$/.exec(path);

  if (method === 'POST' && path === '/api/generate') {
    // Two model calls in real life. The delay is there so loading states are
    // built against something realistic instead of an instant response.
    return respond(MOCK_GENERATE, 1400);
  }

  if (method === 'POST' && path === '/api/generate/summary') {
    return respond({ summary: MOCK_GENERATE.cv.summary }, 700);
  }

  if (method === 'POST' && path === '/api/export') {
    return respond(
      {
        pdf_path: 'storage/output/Shehzar_Abbasi_AirCanada_FrontEndDeveloper_2026-08-16.pdf',
        filename: 'Shehzar_Abbasi_AirCanada_FrontEndDeveloper_2026-08-16.pdf',
        page_count: 1,
      },
      900,
    );
  }

  if (method === 'GET' && path === '/api/applications') {
    return respond([...applications].sort((a, b) => b.created_at.localeCompare(a.created_at)), 400);
  }

  if (method === 'GET' && idMatch) {
    const found = applications.find((a) => a.id === Number(idMatch[1]));
    return found ? respond(found, 300) : notFound(path);
  }

  if (method === 'PATCH' && idMatch) {
    const id = Number(idMatch[1]);
    const status = (body as { status: ApplicationStatus }).status;
    applications = applications.map((a) =>
      a.id === id
        ? { ...a, status, applied_at: a.applied_at ?? new Date().toISOString().slice(0, 19) }
        : a,
    );
    const updated = applications.find((a) => a.id === id);
    return updated ? respond(updated, 250) : notFound(path);
  }

  return null;
}

function respond<T>(body: T, ms: number): Observable<HttpResponse<T>> {
  return of(new HttpResponse({ status: 200, body })).pipe(delay(ms));
}

function notFound(path: string): Observable<never> {
  return throwError(
    () => new HttpErrorResponse({ status: 404, url: path, error: { detail: 'Not found' } }),
  ).pipe(delay(200)) as Observable<never>;
}
