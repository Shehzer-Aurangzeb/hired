import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withInMemoryScrolling } from '@angular/router';

import { routes } from './app.routes';
import { errorInterceptor } from './core/error.interceptor';
import { mockInterceptor } from './core/mock.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(
      routes,
      // Back navigation restores the previous scroll position.
      withInMemoryScrolling({ scrollPositionRestoration: 'enabled', anchorScrolling: 'enabled' }),
    ),
    // error is outermost so it catches failures from both the mock and the real
    // backend. The other way round, a mock error short-circuits before the
    // error interceptor is ever reached and no toast is raised.
    provideHttpClient(withInterceptors([errorInterceptor, mockInterceptor])),
  ],
};
