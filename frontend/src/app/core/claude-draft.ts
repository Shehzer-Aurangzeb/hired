// The full prompt is too long for a URL (it gets cut off), so it goes on the
// clipboard and the URL only carries this short message.
export const BOOTSTRAP =
  'I am filling in a master profile for a CV tool. The full instructions are on ' +
  'my clipboard, paste-ready. Ask me to paste them.';

export const CLAUDE_URL = `https://claude.ai/new?q=${encodeURIComponent(BOOTSTRAP)}`;

/**
 * Copies the prompt, then opens claude.ai. Returns whether the copy worked.
 * Copy must come first: once the new tab takes focus, clipboard writes throw.
 */
export async function openClaude(prompt: string): Promise<boolean> {
  const copied = await copyPrompt(prompt);
  window.open(CLAUDE_URL, '_blank', 'noopener,noreferrer');
  return copied;
}

/** Falls back to execCommand where the clipboard API is missing (non-https). */
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
