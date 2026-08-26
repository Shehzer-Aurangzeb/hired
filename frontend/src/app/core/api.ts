// Same origin, always. In normal use FastAPI serves this bundle itself, so
// there is one port and no CORS; under `ng serve` proxy.conf.json forwards /api
// to the backend so the same relative URL keeps working.
//
// ponytail: no environment files. One constant beats a build-time swap.
export const API = '';

/**
 * Cap on an uploaded profile, enforced before the bytes leave the browser.
 * A profile is plain text and a big one is a mistake, not a large CV.
 */
export const MAX_BYTES = 512 * 1024;
