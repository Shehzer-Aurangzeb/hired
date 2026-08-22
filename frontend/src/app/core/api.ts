// ponytail: no environment files. v1 is localhost only, and the backend already
// allows CORS from 4200, so there is no proxy.conf either.
export const API = 'http://localhost:8000';

/**
 * Generate, export and applications have no backend yet. While this is true,
 * mock.interceptor.ts answers those calls from fixtures. Auth and everything
 * under /api/profile are real and are never mocked.
 *
 * Flip to false once the last of those routes lands.
 */
export const USE_MOCKS = true;


/**
 * Cap on an uploaded profile, enforced before the bytes leave the browser.
 * A profile is plain text and a big one is a mistake, not a large CV.
 */
export const MAX_BYTES = 512 * 1024;
