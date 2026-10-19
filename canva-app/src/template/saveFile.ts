import type { TemplateFile } from "./buildFile";

/**
 * Copies the template's text to the clipboard. Returns false if that is not
 * allowed. (A file download is not offered: Canva's panel does not let a page
 * inside it save files, so the text is what crosses to BetterCricket.)
 */
export async function copyTemplate(file: TemplateFile): Promise<boolean> {
  const text = JSON.stringify(file);
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Some embedded pages refuse the clipboard API; the old route may still work.
    try {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    } catch {
      return false;
    }
  }
}
