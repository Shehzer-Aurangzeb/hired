import { httpResource } from '@angular/common/http';
import { Injectable } from '@angular/core';

import { API } from './api';
import { Profile } from './models';

@Injectable({ providedIn: 'root' })
export class ProfileService {
  // ponytail: httpResource gives value/error/isLoading signals in one line. It is
  // experimental in v20; swap for toSignal + catchError if the API churns.
  readonly profile = httpResource<Profile>(() => `${API}/api/profile`);
}
