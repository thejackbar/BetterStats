import type { Picture } from "./exportFlow";

const readAsDataUrl = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("The picture could not be read."));
    reader.readAsDataURL(blob);
  });

/**
 * Downloads the picture Canva exported and returns it as a data URL, which is
 * how the template file carries it. Refuses anything that is not a single image
 * (a multi-page design exports as a ZIP), because BetterCricket could not use it.
 */
export async function fetchPicture(url: string): Promise<Picture> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(
      `Canva's picture could not be downloaded (HTTP ${res.status}).`,
    );
  }
  const blob = await res.blob();
  if (!/^image\/(png|jpeg)$/.test(blob.type)) {
    throw new Error(
      `Canva gave a ${blob.type || "unknown"} file, not a picture. Use a design with one page and export it as PNG or JPG.`,
    );
  }
  return { dataUrl: await readAsDataUrl(blob), bytes: blob.size };
}
