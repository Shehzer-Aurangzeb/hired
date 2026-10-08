// Always same origin: FastAPI serves the bundle, and under `ng serve`
// proxy.conf.json forwards /api to the backend.
export const API = '';

/** Max profile upload size, checked before sending. */
export const MAX_BYTES = 512 * 1024;
