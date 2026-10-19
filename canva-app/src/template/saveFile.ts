import type { TemplateFile } from "./buildFile";

/** A safe file name for a template: letters, numbers, dashes. */
export function fileNameFor(name: string): string {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${base || "template"}.bettercricket.json`;
}

/** Offers the template as a download. Returns false if the browser refused. */
export function downloadTemplate(file: TemplateFile): boolean {
  try {
    const blob = new Blob([JSON.stringify(file)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileNameFor(file.name);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    return true;
  } catch {
    return false;
  }
}

/** Copies the template's text to the clipboard. Returns false if that is not allowed. */
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
