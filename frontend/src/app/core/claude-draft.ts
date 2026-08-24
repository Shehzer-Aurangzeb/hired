/**
 * "Draft it with Claude" — hands the starter file plus a briefing to claude.ai.
 *
 * Deliberately a link out rather than a server-side call: writing this file is a
 * conversation, it needs your memory rather than the app's, and nothing Claude
 * produces reaches the profile without you reading it and pressing Save.
 *
 * The prompt itself comes from the backend, so rewording it is a config change.
 */

/**
 * The prompt is ~33KB, near 49KB once URL-encoded, and a request line that long
 * is refused or quietly cut short well before it reaches Claude. Truncation is
 * the dangerous half: an interview running against half a template looks like it
 * is working. So the clipboard carries the prompt and the URL carries this.
 */
export const BOOTSTRAP =
  'I am filling in a master profile for a CV tool. The full instructions are on ' +
  'my clipboard, paste-ready. Ask me to paste them.';

export const CLAUDE_URL = `https://claude.ai/new?q=${encodeURIComponent(BOOTSTRAP)}`;

/**
 * Copies the prompt, then opens the chat. Returns whether the copy landed, which
 * is the half the caller has to tell the user about: the tab opens either way and
 * a bootstrap with nothing on the clipboard behind it is worse than no tab.
 *
 * Copy first on purpose. The clipboard API needs a focused document, and the new
 * tab takes focus, so writing afterwards throws. Opening after the await still
 * counts as user-initiated: transient activation outlives a clipboard write.
 */
export async function openClaude(prompt: string): Promise<boolean> {
  const copied = await copyPrompt(prompt);
  window.open(CLAUDE_URL, '_blank', 'noopener,noreferrer');
  return copied;
}

/**
 * Falls back to a hidden textarea where the clipboard API is unavailable, which
 * is any page not served over https or localhost.
 */
export async function copyPrompt(prompt: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(prompt);
    return true;
  } catch {
    const area = document.createElement('textarea');
    area.value = prompt;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  }
}
