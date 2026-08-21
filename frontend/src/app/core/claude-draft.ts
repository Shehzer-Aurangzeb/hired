/**
 * "Draft it with Claude" — hands the template plus a briefing to claude.ai and
 * lets you paste the result back.
 *
 * Deliberately a link out rather than a server-side call: writing this file is
 * a conversation, it needs your memory not the app's, and nothing generated
 * reaches the profile without you reading it and pressing Save.
 */

/** The briefing. The template follows it, so Claude has the exact target shape. */
export function claudePrompt(template: string): string {
  return `I am filling in the "master profile" for a CV tailoring tool called hired. The tool builds a one-page CV for a specific job posting by *selecting* from bullets I have already written. It never writes new claims. So this file may only contain things I can defend in an interview.

Interview me one section at a time. Ask about my work history before anything else, since it is the bulk of the file. When we are done, output the finished file as one markdown code block I can copy back into the app.

Rules that matter more than completeness:

- Never invent a metric, a technology, or a responsibility. If I do not give you a number, do not add one. An empty field is fine; a plausible guess is not.
- Every project needs a claim_boundary, and cannot_claim is the important half: the adjacent things I did NOT do. Ask me for those explicitly, because I will forget to volunteer them.
- required_qualifiers holds wording that must always travel with a claim, for example that a figure is estimated rather than measured.
- Bullets are verb-first, no first person, one accomplishment each.
- Give every bullet and project a stable lowercase id with hyphens.
- Mark a bullet "status: blocked" if I say I cannot back it up yet.

Format rules, because the file is parsed strictly:

- Keep the section names, heading levels and field names exactly as they appear below.
- Section bodies are YAML. Any value containing a colon, or starting with a quote, must be wrapped in single quotes end to end.
- Leave out a field rather than filling it with a placeholder.

Here is the template to fill in, and the exact shape to return:

${template}`;
}

/**
 * Opens claude.ai with the prompt prefilled, and copies it as well: the query
 * parameter is long and not something we control, so the clipboard is the copy
 * that always works.
 */
export function openClaude(template: string): void {
  const prompt = claudePrompt(template);
  navigator.clipboard?.writeText(prompt).catch(() => undefined);
  window.open(
    `https://claude.ai/new?q=${encodeURIComponent(prompt)}`,
    '_blank',
    'noopener,noreferrer',
  );
}
