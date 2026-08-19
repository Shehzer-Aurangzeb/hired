import { CdkDrag, CdkDragHandle, CdkDropList, CdkDropListGroup, moveItemInArray } from '@angular/cdk/drag-drop';
import type { CdkDragDrop } from '@angular/cdk/drag-drop';
import { ChangeDetectionStrategy, Component, model } from '@angular/core';

import { CvSection, SelectedBullet } from '../../core/models';
import { Icon } from '../../shared/icon';

/**
 * Owns bullet order and inclusion. Deselecting keeps the bullet in the list so
 * it can be put back, which is why exclusion is a separate set rather than a
 * removal from `sections`.
 */
@Component({
  selector: 'app-bullet-selector',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CdkDropList, CdkDropListGroup, CdkDrag, CdkDragHandle, Icon],
  templateUrl: './bullet-selector.html',
})
export class BulletSelector {
  readonly sections = model.required<CvSection[]>();
  readonly excluded = model.required<Set<string>>();

  isOn(id: string): boolean {
    return !this.excluded().has(id);
  }

  toggle(id: string): void {
    this.excluded.update((set) => {
      const next = new Set(set);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  activeCount(section: CvSection): number {
    return section.bullets.filter((b) => this.isOn(b.id)).length;
  }

  onDrop(sectionIndex: number, event: CdkDragDrop<SelectedBullet[]>): void {
    this.move(sectionIndex, event.previousIndex, event.currentIndex);
  }

  /** Keyboard path for reordering. Drag-drop alone locks out keyboard users. */
  nudge(sectionIndex: number, from: number, delta: -1 | 1): void {
    const to = from + delta;
    const length = this.sections()[sectionIndex].bullets.length;
    if (to >= 0 && to < length) {
      this.move(sectionIndex, from, to);
    }
  }

  private move(sectionIndex: number, from: number, to: number): void {
    if (from === to) {
      return;
    }
    this.sections.update((sections) =>
      sections.map((section, i) => {
        if (i !== sectionIndex) {
          return section;
        }
        const bullets = [...section.bullets];
        moveItemInArray(bullets, from, to);
        return { ...section, bullets };
      }),
    );
  }
}
