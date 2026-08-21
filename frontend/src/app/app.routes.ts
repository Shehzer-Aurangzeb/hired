import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth.guard';
import { profileGuard, setupGuard } from './core/profile.guard';

export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in · hired',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/lock/lock-page').then((m) => m.LockPage),
  },
  {
    path: 'setup',
    title: 'Set up · hired',
    canActivate: [authGuard, setupGuard],
    loadComponent: () =>
      import('./features/onboarding/onboarding-page').then((m) => m.OnboardingPage),
  },
  {
    path: 'generate',
    canActivate: [authGuard, profileGuard],
    title: 'Generate · hired',
    loadComponent: () => import('./features/generate/generate-page').then((m) => m.GeneratePage),
  },
  {
    path: 'applications',
    canActivate: [authGuard, profileGuard],
    title: 'Applications · hired',
    loadComponent: () =>
      import('./features/applications/applications-page').then((m) => m.ApplicationsPage),
  },
  {
    path: 'applications/:id',
    canActivate: [authGuard, profileGuard],
    title: 'Application · hired',
    loadComponent: () =>
      import('./features/applications/application-detail').then((m) => m.ApplicationDetail),
  },
  {
    path: 'profile',
    canActivate: [authGuard, profileGuard],
    title: 'Profile · hired',
    loadComponent: () => import('./features/profile/profile-page').then((m) => m.ProfilePage),
    // The profile is the only copy of the CV data, so leaving mid-edit asks first.
    canDeactivate: [
      (page: import('./features/profile/profile-page').ProfilePage) => page.confirmLeave(),
    ],
  },
  { path: '', pathMatch: 'full', redirectTo: 'generate' },
  { path: '**', redirectTo: 'generate' },
];
