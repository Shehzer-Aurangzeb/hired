import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: 'generate',
    title: 'Generate · hired',
    loadComponent: () => import('./features/generate/generate-page').then((m) => m.GeneratePage),
  },
  {
    path: 'applications',
    title: 'Applications · hired',
    loadComponent: () =>
      import('./features/applications/applications-page').then((m) => m.ApplicationsPage),
  },
  {
    path: 'applications/:id',
    title: 'Application · hired',
    loadComponent: () =>
      import('./features/applications/application-detail').then((m) => m.ApplicationDetail),
  },
  {
    path: 'profile',
    title: 'Profile · hired',
    loadComponent: () => import('./features/profile/profile-page').then((m) => m.ProfilePage),
  },
  { path: '', pathMatch: 'full', redirectTo: 'generate' },
  { path: '**', redirectTo: 'generate' },
];
