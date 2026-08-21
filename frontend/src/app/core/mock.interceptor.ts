import { HttpErrorResponse, HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { Observable, delay, of, throwError } from 'rxjs';

import { MOCK_PASSWORD, USE_MOCKS } from './api';
import { Application } from './models';
import { MOCK_APPLICATIONS, MOCK_GENERATE, mockGenerate } from './mock-data';
import { PROFILE_TEMPLATE } from '../features/onboarding/template';
import { ProfileIssue, ValidationResult } from './models';

// ponytail: module-level array, not a service. Mock state lives exactly as long
// as the tab does, which is the point. Delete this file when the backend lands.
let applications: Application[] = MOCK_APPLICATIONS.map((a) => ({ ...a }));

// The real session is an httpOnly cookie and survives a reload, so the stand-in
// has to as well or every refresh signs you out. Lockout state is not persisted:
// a page reload clearing it matches nothing real, but it keeps the demo usable.
const SESSION_KEY = 'hired-mock-session';
const PROFILE_KEY = 'hired-mock-profile';
const PROFILE_AT_KEY = 'hired-mock-profile-at';
const LOCKOUT_MS = 30_000;
let failures = 0;
let lockedUntil = 0;

function signedIn(): boolean {
  return sessionStorage.getItem(SESSION_KEY) === '1';
}

function setSignedIn(value: boolean): void {
  if (value) {
    sessionStorage.setItem(SESSION_KEY, '1');
  } else {
    sessionStorage.removeItem(SESSION_KEY);
  }
}

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
    '[hired] mocks on. Scenarios: ?mock=weak | blocked | overflow | error | empty | conflict',
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

  if (method === 'GET' && path === '/api/auth/session') {
    return respond({ authenticated: signedIn() }, 250);
  }

  if (method === 'POST' && path === '/api/auth/login') {
    // Three misses and the real backend will rate limit, so the mock does too.
    // The lockout has to expire on its own: a counter that only resets on a
    // correct password locks you out of ever giving one.
    const left = lockedUntil - Date.now();
    if (left > 0) {
      return failWith(429, 'Too many attempts. Wait a moment before trying again.', path, {
        retry_after: Math.ceil(left / 1000),
      });
    }
    if ((body as { password: string }).password === MOCK_PASSWORD) {
      setSignedIn(true);
      failures = 0;
      return respond({ authenticated: true }, 600);
    }
    failures += 1;
    if (failures >= 3) {
      failures = 0;
      lockedUntil = Date.now() + LOCKOUT_MS;
      return failWith(429, 'Too many attempts. Wait a moment before trying again.', path, {
        retry_after: LOCKOUT_MS / 1000,
      });
    }
    return failWith(401, 'That password is not right.', path);
  }

  if (method === 'GET' && path === '/api/profile/source') {
    const text = sessionStorage.getItem(PROFILE_KEY);
    return respond(
      { text: text ?? '', exists: !!text, updated_at: sessionStorage.getItem(PROFILE_AT_KEY) },
      300,
    );
  }

  if (method === 'GET' && path === '/api/profile/template') {
    return respond({ text: PROFILE_TEMPLATE }, 200);
  }

  if (method === 'POST' && path === '/api/profile/validate') {
    return respond(checkProfile((body as { text: string }).text), 500);
  }

  if (method === 'PUT' && path === '/api/profile/source') {
    const { text, expected_updated_at } = body as {
      text: string;
      expected_updated_at: string | null;
    };
    const stored = sessionStorage.getItem(PROFILE_AT_KEY);
    // A save composed against an older copy would silently overwrite whatever
    // landed in between, so it is refused with the current text attached.
    const stale = stored && expected_updated_at && expected_updated_at !== stored;
    if (stale || scenario() === 'conflict') {
      return failWith(409, 'This profile changed somewhere else since you opened it.', path, {
        text: sessionStorage.getItem(PROFILE_KEY) ?? '',
        updated_at: stored,
      });
    }
    const result = checkProfile(text);
    if (!result.ok) {
      return failWith(422, 'The profile did not parse.', path, { errors: result.errors });
    }
    const at = new Date().toISOString();
    sessionStorage.setItem(PROFILE_KEY, text);
    sessionStorage.setItem(PROFILE_AT_KEY, at);
    return respond({ text, exists: true, updated_at: at }, 500);
  }

  if (method === 'POST' && path === '/api/auth/logout') {
    setSignedIn(false);
    return respond({ authenticated: false }, 150);
  }

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

/**
 * Stand-in for the real parser. Catches the mistakes that actually happen when
 * hand-writing this file, including the quoting trap that broke it once already.
 *
 * ponytail: line scanning, not a YAML parse. The backend does the real thing;
 * this exists so the UI has something honest to render before then.
 */
function checkProfile(text: string): ValidationResult {
  const lines = text.split('\n');
  const errors: ProfileIssue[] = [];
  const warnings: ProfileIssue[] = [];

  if (!/^# Identity$/m.test(text)) {
    errors.push({ line: null, message: 'No "# Identity" section. Every profile needs one.' });
  }
  if (!/^name:\s*\S/m.test(text)) {
    errors.push({ line: null, message: 'Identity has no name.' });
  }

  lines.forEach((line, i) => {
    // - "quoted phrase" trailing words  ->  YAML sees two scalars and gives up
    if (/^\s*-\s+".*"\s+\S/.test(line)) {
      errors.push({
        line: i + 1,
        message:
          'A list item that starts with a quote must be quoted end to end. Wrap the whole value in single quotes.',
      });
    }
    if (/\t/.test(line)) {
      errors.push({ line: i + 1, message: 'Tab character. YAML wants spaces.' });
    }
  });

  const projects = text.split(/^### /m).slice(1);
  const bullets = (text.match(/^\s+- id:/gm) ?? []).length;
  const missing = projects.filter((p) => !/claim_boundary:/.test(p)).length;

  if (missing) {
    warnings.push({
      line: null,
      message: `${missing} project${missing === 1 ? '' : 's'} without a claim_boundary. The guard cannot protect what has no boundary.`,
    });
  }
  if (!projects.length) {
    warnings.push({ line: null, message: 'No projects yet, so there is nothing to select from.' });
  }

  return {
    ok: errors.length === 0,
    errors,
    warnings,
    summary: {
      projects: projects.length,
      bullets,
      blocked: (text.match(/status:\s*blocked/g) ?? []).length,
      missing_boundaries: missing,
    },
  };
}

function respond<T>(body: T, ms: number): Observable<HttpResponse<T>> {
  return of(new HttpResponse({ status: 200, body })).pipe(delay(ms));
}

function notFound(path: string): Observable<never> {
  return fail(404, 'Not found', path);
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
