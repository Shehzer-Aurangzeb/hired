// ponytail: no environment files. v1 is localhost only, and the backend already
// allows CORS from 4200, so there is no proxy.conf either.
export const API = 'http://localhost:8000';

/**
 * Generate, export and applications have no backend yet (Phases 5, 6 and 9).
 * While this is true, mock.interceptor.ts answers those calls from fixtures.
 * GET /api/profile is real and is never mocked.
 *
 * Flip to false as each backend route lands.
 */
export const USE_MOCKS = true;

/**
 * Only used while USE_MOCKS is on. The real password is hashed in the database
 * and never reaches the browser; this exists so the demo has something to type.
 */
export const MOCK_PASSWORD = 'hired';
