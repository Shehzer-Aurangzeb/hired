/**
 * "Draft it with Claude" — hands the starter file plus a briefing to claude.ai.
 *
 * Deliberately a link out rather than a server-side call: writing this file is a
 * conversation, it needs your memory rather than the app's, and nothing Claude
 * produces reaches the profile without you reading it and pressing Save.
 *
 * The prompt itself comes from the backend, so rewording it is a config change.
 */

/** Opens claude.ai with the prompt prefilled. */
export function openClaude(prompt: string): void {
  window.open(
    `https://claude.ai/new?q=${encodeURIComponent(prompt)}`,
    '_blank',
    'noopener,noreferrer',
  );
}

/**
 * The query parameter is long and not a contract we control, so copying is the
 * route that always works. Falls back to a hidden textarea where the clipboard
 * API is unavailable, which is any page not served over https or localhost.
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
