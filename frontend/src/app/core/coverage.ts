import { ParsedJd, RequiredSkill, SkillCoverage } from './models';

export interface Coverage {
  name: string;
  importance: number;
  required: boolean;
  /** The word appears on the page (what a keyword filter sees). */
  covered: boolean;
  /** A printed bullet backs it up. */
  evidenced: boolean;
  bulletIds: string[];
}

/**
 * Checks each requirement two ways: `covered` is a plain substring scan (like an ATS),
 * `evidenced` comes from the server's map of which printed bullets back it.
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
