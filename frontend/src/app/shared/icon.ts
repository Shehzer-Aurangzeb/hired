import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type IconName =
  | 'sparkles'
  | 'file-text'
  | 'user'
  | 'grip'
  | 'alert'
  | 'ban'
  | 'check'
  | 'download'
  | 'chevron-right'
  | 'arrow-left'
  | 'refresh'
  | 'search'
  | 'x'
  | 'lock'
  | 'log-out'
  | 'eye'
  | 'eye-off'
  | 'history'
  | 'mail'
  | 'linkedin'
  | 'github'
  | 'globe'
  | 'upload'
  | 'more'
  | 'claude';

/**
 * Inline SVG from the Lucide set, drawn with @switch.
 * ponytail: 18 icons do not justify a dependency, and inlining avoids the
 * DomSanitizer dance that a path-map version would need.
 */
@Component({
  selector: 'app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'inline-flex shrink-0' },
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      @switch (name()) {
        @case ('claude') {
          <!-- The Claude burst, drawn with the shared stroke settings rather
               than dropped in as brand artwork. -->
          <path d="M14.2 12.0L21.6 12.0" />
          <path d="M13.9 13.1L20.3 16.8" />
          <path d="M13.1 13.9L16.8 20.3" />
          <path d="M12.0 14.2L12.0 21.6" />
          <path d="M10.9 13.9L7.2 20.3" />
          <path d="M10.1 13.1L3.7 16.8" />
          <path d="M9.8 12.0L2.4 12.0" />
          <path d="M10.1 10.9L3.7 7.2" />
          <path d="M10.9 10.1L7.2 3.7" />
          <path d="M12.0 9.8L12.0 2.4" />
          <path d="M13.1 10.1L16.8 3.7" />
          <path d="M13.9 10.9L20.3 7.2" />
        }
        @case ('sparkles') {
          <path
            d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"
          />
        }
        @case ('file-text') {
          <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z" />
          <path d="M14 2v5h5" />
          <path d="M9 13h6" />
          <path d="M9 17h6" />
        }
        @case ('user') {
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        }
        @case ('grip') {
          <circle cx="9" cy="6" r="1" />
          <circle cx="9" cy="12" r="1" />
          <circle cx="9" cy="18" r="1" />
          <circle cx="15" cy="6" r="1" />
          <circle cx="15" cy="12" r="1" />
          <circle cx="15" cy="18" r="1" />
        }
        @case ('alert') {
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
          <path d="M12 9v4" />
          <path d="M12 17h.01" />
        }
        @case ('ban') {
          <circle cx="12" cy="12" r="10" />
          <path d="m4.9 4.9 14.2 14.2" />
        }
        @case ('check') {
          <path d="M20 6 9 17l-5-5" />
        }
        @case ('download') {
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <path d="m7 10 5 5 5-5" />
          <path d="M12 15V3" />
        }
        @case ('chevron-right') {
          <path d="m9 18 6-6-6-6" />
        }
        @case ('arrow-left') {
          <path d="m12 19-7-7 7-7" />
          <path d="M19 12H5" />
        }
        @case ('refresh') {
          <path d="M3 12a9 9 0 0 1 9-9 9 9 0 0 1 6.7 3L21 8" />
          <path d="M21 3v5h-5" />
          <path d="M21 12a9 9 0 0 1-9 9 9 9 0 0 1-6.7-3L3 16" />
          <path d="M3 21v-5h5" />
        }
        @case ('mail') {
          <rect x="2" y="4" width="20" height="16" rx="2" />
          <path d="m2 7 10 6 10-6" />
        }
        @case ('linkedin') {
          <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-10h4v1.5A4 4 0 0 1 16 8z" />
          <rect x="2" y="9" width="4" height="12" />
          <circle cx="4" cy="4" r="2" />
        }
        @case ('github') {
          <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5a4.3 4.3 0 0 0-1.2-3 4 4 0 0 0-.1-3S17.5 2.5 15 4a13 13 0 0 0-6 0C6.5 2.5 5.3 3 5.3 3a4 4 0 0 0-.1 3A4.3 4.3 0 0 0 4 9c0 3.5 3 5.5 6 5.5a4.8 4.8 0 0 0-1 3.5v4" />
          <path d="M9 18c-4 1.5-4-2-6-2" />
        }
        @case ('globe') {
          <circle cx="12" cy="12" r="10" />
          <path d="M2 12h20" />
          <path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20" />
        }
        @case ('upload') {
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <path d="m7 9 5-5 5 5" />
          <path d="M12 4v12" />
        }
        @case ('history') {
          <path d="M3 12a9 9 0 1 0 2.6-6.4L3 8" />
          <path d="M3 3v5h5" />
          <path d="M12 7v5l3 2" />
        }
        @case ('more') {
          <circle cx="12" cy="5" r="1" fill="currentColor" />
          <circle cx="12" cy="12" r="1" fill="currentColor" />
          <circle cx="12" cy="19" r="1" fill="currentColor" />
        }
        @case ('search') {
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        }
        @case ('x') {
          <path d="M18 6 6 18" />
          <path d="m6 6 12 12" />
        }
        @case ('lock') {
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        }
        @case ('log-out') {
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <path d="m16 17 5-5-5-5" />
          <path d="M21 12H9" />
        }
        @case ('eye') {
          <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7" />
          <circle cx="12" cy="12" r="3" />
        }
        @case ('eye-off') {
          <path d="M10.7 5.1A9.9 9.9 0 0 1 12 5c6.4 0 10 7 10 7a15.5 15.5 0 0 1-3.4 4.2" />
          <path d="M6.6 6.6A15.6 15.6 0 0 0 2 12s3.6 7 10 7a9.8 9.8 0 0 0 5.4-1.6" />
          <path d="m2 2 20 20" />
          <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
        }
      }
    </svg>
  `,
})
export class Icon {
  readonly name = input.required<IconName>();
  readonly size = input(16);
}
