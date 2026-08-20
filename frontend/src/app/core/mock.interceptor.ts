import { HttpErrorResponse, HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { Observable, delay, of, throwError } from 'rxjs';

import { USE_MOCKS } from './api';
import { Application } from './models';
import { MOCK_APPLICATIONS, MOCK_GENERATE, mockGenerate } from './mock-data';

// ponytail: module-level array, not a service. Mock state lives exactly as long
// as the tab does, which is the point. Delete this file when the backend lands.
let applications: Application[] = MOCK_APPLICATIONS.map((a) => ({ ...a }));

/**
 * ?mock=<name> switches fixtures, so the states the happy path never reaches can
 * actually be looked at: weak, blocked, overflow, error, empty.
 * Read per request rather than at load, so it follows navigation.
 */
function scenario(): string {
  return new URLSearchParams(location.search).get('mock') ?? '';
}

if (USE_MOCKS) {
  console.info(
    '[hired] mocks on. Scenarios: ?mock=weak | blocked | overflow | error | empty',
  );
}

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
    if (scenario() === 'error') {
      return fail(500, 'The selector returned malformed JSON.', path);
    }
    // Two model calls in real life. The delay is there so loading states are
    // built against something realistic instead of an instant response.
    return respond(mockGenerate(scenario()), 1400);
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
    if (scenario() === 'empty') {
      return respond([], 400);
    }
    return respond([...applications].sort((a, b) => b.created_at.localeCompare(a.created_at)), 400);
  }

  if (method === 'GET' && idMatch) {
    const found = applications.find((a) => a.id === Number(idMatch[1]));
    return found ? respond(found, 300) : notFound(path);
  }

  if (method === 'PATCH' && idMatch) {
    const id = Number(idMatch[1]);
    const changes = body as Partial<Application>;
    applications = applications.map((a) =>
      a.id === id
        ? {
            ...a,
            ...changes,
            // Leaving 'generated' is the moment it was actually sent.
            applied_at:
              changes.status && changes.status !== 'generated'
                ? (a.applied_at ?? new Date().toISOString().slice(0, 19))
                : a.applied_at,
          }
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
  return fail(404, 'Not found', path);
}

function fail(status: number, detail: string, path: string): Observable<never> {
  return throwError(
    () => new HttpErrorResponse({ status, url: path, error: { detail } }),
  ).pipe(delay(400)) as Observable<never>;
}
