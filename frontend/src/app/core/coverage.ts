import { ParsedJd, RequiredSkill } from './models';

export interface Coverage {
  name: string;
  importance: number;
  required: boolean;
  /** Appears anywhere on the page. What a keyword scan sees. */
  covered: boolean;
  /** Appears inside a bullet. What you can point at when asked. */
  evidenced: boolean;
}

/**
 * What the posting asked for, against what the page said. Two levels, because
 * they answer different questions: a skill on the skills line is visible to a
 * keyword scan, but only a bullet describing the work is defensible.
 *
 * Takes plain strings rather than a CV shape, so the generate page (a fresh
 * GeneratedCv) and the detail page (a saved Application) can both call it.
 *
 * ponytail: case-insensitive substring match. "React" hits "React Native", and
 * a posting saying "ReactJS" misses "React" on the page. The synonym map planned
 * for `profile/skills_taxonomy.md` is the upgrade path.
 */
export function computeCoverage(jd: ParsedJd, bulletText: string, pageText: string): Coverage[] {
  const evidence = bulletText.toLowerCase();
  const page = pageText.toLowerCase();

  const check = (skill: RequiredSkill, required: boolean): Coverage => {
    const needle = skill.name.toLowerCase();
    return {
      name: skill.name,
      importance: skill.importance,
      required,
      covered: page.includes(needle),
      evidenced: evidence.includes(needle),
    };
  };

  return [
    ...jd.required_skills.map((s) => check(s, true)),
    ...jd.preferred_skills.map((s) => check(s, false)),
  ];
}
