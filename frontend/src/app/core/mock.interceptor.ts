import { HttpErrorResponse, HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { Observable, delay, of, throwError } from 'rxjs';

import { USE_MOCKS } from './api';
import { MOCK_GENERATE, mockGenerate } from './mock-data';


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
    '[hired] mocks on. Scenarios: ?mock=weak | blocked | overflow | error',
  );
}

/**
 * Answers generate and export, the last two routes with no backend.
 * Auth, the profile and applications are real and fall through.
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
        filename: 'Shehzar_Abbasi_AirCanada_FrontEndDeveloper_2026-08-16.pdf',
        page_count: 1,
      },
      900,
    );
  }

  return null;
}

function respond<T>(body: T, ms: number): Observable<HttpResponse<T>> {
  return of(new HttpResponse({ status: 200, body })).pipe(delay(ms));
}

function fail(status: number, detail: string, path: string): Observable<never> {
  return failWith(status, detail, path);
}

function failWith(
  status: number,
  detail: string,
  path: string,
  extra: Record<string, unknown> = {},
): Observable<never> {
  return throwError(
    () => new HttpErrorResponse({ status, url: path, error: { detail, ...extra } }),
  ).pipe(delay(400)) as Observable<never>;
}
