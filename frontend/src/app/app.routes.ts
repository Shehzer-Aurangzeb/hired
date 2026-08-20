import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in · hired',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/lock/lock-page').then((m) => m.LockPage),
  },
  {
    path: 'generate',
    canActivate: [authGuard],
    title: 'Generate · hired',
    loadComponent: () => import('./features/generate/generate-page').then((m) => m.GeneratePage),
  },
  {
    path: 'applications',
    canActivate: [authGuard],
    title: 'Applications · hired',
    loadComponent: () =>
      import('./features/applications/applications-page').then((m) => m.ApplicationsPage),
  },
  {
    path: 'applications/:id',
    canActivate: [authGuard],
    title: 'Application · hired',
    loadComponent: () =>
      import('./features/applications/application-detail').then((m) => m.ApplicationDetail),
  },
  {
    path: 'profile',
    canActivate: [authGuard],
    title: 'Profile · hired',
    loadComponent: () => import('./features/profile/profile-page').then((m) => m.ProfilePage),
  },
  { path: '', pathMatch: 'full', redirectTo: 'generate' },
  { path: '**', redirectTo: 'generate' },
];
