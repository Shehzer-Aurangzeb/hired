import { ParsedJd, RequiredSkill, SkillCoverage } from './models';

export interface Coverage {
  name: string;
  importance: number;
  required: boolean;
  /** The word appears on the page (what a keyword filter sees). */
  covered: boolean;
  /** A printed bullet backs it up, or the profile answers it another way. */
  evidenced: boolean;
  /** For a requirement no bullet can back: the degree that meets it, or why none can. */
  backedBy: string;
  /** The model says a bullet backs it, but the words appear nowhere on the page.
   *  A judgement you can't check by reading, so it is marked rather than hidden. */
  byMeaning: boolean;
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
  // A degree or a disposition is answered by the profile, or by nothing a CV
  // can show. Either way no bullet backs it, so a cross would be a lie.
  const byName = new Map(backing.map((c) => [c.skill.trim().toLowerCase(), c.backed_by ?? '']));

  const check = (skill: RequiredSkill, required: boolean): Coverage => {
    const key = skill.name.trim().toLowerCase();
    const bulletIds = bySkill.get(key) ?? [];
    const backedBy = byName.get(key) ?? '';
    const literal = page.includes(skill.name.toLowerCase());
    return {
      name: skill.name,
      importance: skill.importance,
      required,
      covered: literal || bulletIds.length > 0 || !!backedBy,
      evidenced: bulletIds.length > 0 || !!backedBy,
      backedBy,
      byMeaning: bulletIds.length > 0 && !literal,
      bulletIds,
    };
  };

  return [
    ...jd.required_skills.map((s) => check(s, true)),
    ...jd.preferred_skills.map((s) => check(s, false)),
  ];
}
