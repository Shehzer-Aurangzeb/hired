import { ParsedJd, RequiredSkill, SkillCoverage } from './models';

export interface Coverage {
  name: string;
  importance: number;
  required: boolean;
  /** The word appears somewhere on the page. What a keyword scan sees. */
  covered: boolean;
  /** A bullet on the page backs it. What you can point at when asked. */
  evidenced: boolean;
  /** Which bullets, so the UI can say where the evidence is. */
  bulletIds: string[];
}

/**
 * What the posting asked for, against what the page said. Two levels, because
 * they answer different questions.
 *
 * `covered` is a literal substring scan, and deliberately stays one: it is the
 * ATS question, "would a filter matching this word see it". Being wrong the way
 * a keyword filter is wrong is the correct behaviour for that column.
 *
 * `evidenced` is the interview question, and cannot be answered by looking for
 * words. A posting asking for "mobile app development" is backed by a bullet
 * about shipping a React Native app to both stores, and no substring match will
 * ever find that. So it comes from the selector, which read the posting and
 * every bullet and said which ones back which requirement, checked server-side
 * against the ids that actually printed.
 *
 * Takes plain strings and the stored map rather than a CV shape, so the generate
 * page (a fresh GeneratedCv) and the detail page (a saved Application) can both
 * call it.
 */
export function computeCoverage(
  jd: ParsedJd,
  backing: SkillCoverage[],
  pageText: string,
): Coverage[] {
  const page = pageText.toLowerCase();
  const bySkill = new Map(backing.map((c) => [c.skill.trim().toLowerCase(), c.bullet_ids]));

  const check = (skill: RequiredSkill, required: boolean): Coverage => {
    const bulletIds = bySkill.get(skill.name.trim().toLowerCase()) ?? [];
    return {
      name: skill.name,
      importance: skill.importance,
      required,
      covered: page.includes(skill.name.toLowerCase()) || bulletIds.length > 0,
      evidenced: bulletIds.length > 0,
      bulletIds,
    };
  };

  return [
    ...jd.required_skills.map((s) => check(s, true)),
    ...jd.preferred_skills.map((s) => check(s, false)),
  ];
}
