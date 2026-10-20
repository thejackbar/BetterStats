import { getTemporaryUrl } from "@canva/asset";
import type { ImageRef } from "@canva/asset";
import type { Picture, PictureUse } from "./exportFlow";

// BetterCricket takes pictures up to 5 MB and draws a post 1080 wide, so a picture
// is brought down to a size that suits, which also keeps the pasted text small.
const LIMIT = 5 * 1024 * 1024;
const LONGEST_SIDE: Record<PictureUse, number> = {
  background: 1920,
  panel: 1600,
};
const SHRINK_STEPS = [1, 0.75, 0.55, 0.4];

const loadImage = (src: string, cors: boolean): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const img = new Image();
    if (cors) {
      img.crossOrigin = "anonymous";
    }
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("The picture could not be opened."));
    img.src = src;
  });

/** Downloads the picture as a blob, or null when the app is not allowed to. */
async function downloadBlob(url: string): Promise<Blob | null> {
  try {
    const res = await fetch(url);
    return res.ok ? await res.blob() : null;
  } catch {
    return null;
  }
}

/** Canva's own words for why it would not hand over a picture, in plain terms. */
export function refusal(e: unknown): string {
  const detail = e instanceof Error ? e.message : String(e);
  if (/missing_scope|scope/i.test(detail)) {
    return "Canva says the app is missing the permission to read your pictures (canva:asset:private:read). Add it under Scopes in the Developer Portal, then reload the app.";
  }
  return `Canva would not give the app this picture (${detail || "no reason given"}). It may be a Canva library photo the app is not allowed to read. Upload your own copy into the design, or add the background in BetterPosts.`;
}

/**
 * Brings one of the design's own pictures across by its Canva id: asks Canva for a
 * temporary link, downloads it, and redraws it at a size BetterCricket takes. A
 * picture with see-through parts stays a PNG so they stay see-through; a flat one
 * becomes a JPG, which is far smaller. Throws a plain sentence when it cannot.
 */
export async function fetchImage(
  ref: string,
  use: PictureUse,
): Promise<Picture> {
  let url: string;
  try {
    const got = await getTemporaryUrl({ type: "image", ref: ref as ImageRef });
    url = got.url;
  } catch (e) {
    throw new Error(refusal(e));
  }
  const blob = await downloadBlob(url);
  const img = blob
    ? await loadImage(URL.createObjectURL(blob), false)
    : await loadImage(url, true).catch(() => {
        throw new Error(
          "The picture could not be downloaded from inside Canva.",
        );
      });
  const longest = Math.max(img.naturalWidth, img.naturalHeight);
  if (!longest) {
    throw new Error("The picture has no size.");
  }
  const base = Math.min(1, LONGEST_SIDE[use] / longest);
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("The picture could not be redrawn.");
  }
  let last: Picture | null = null;
  for (const step of SHRINK_STEPS) {
    canvas.width = Math.max(1, Math.round(img.naturalWidth * base * step));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * base * step));
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    let dataUrl: string;
    try {
      // PNG keeps see-through parts; a picture with none is sent as a JPG.
      dataUrl = hasSeeThrough(ctx, canvas.width, canvas.height)
        ? canvas.toDataURL("image/png")
        : canvas.toDataURL("image/jpeg", 0.88);
    } catch {
      throw new Error("The picture could not be read out of Canva.");
    }
    last = { dataUrl, bytes: Math.round((dataUrl.length * 3) / 4) };
    if (last.bytes <= LIMIT) {
      return last;
    }
  }
  if (last) {
    return last;
  }
  throw new Error("The picture could not be redrawn.");
}

/** Whether any pixel on a coarse grid is not fully solid. */
function hasSeeThrough(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
): boolean {
  const stepX = Math.max(1, Math.floor(w / 64));
  const stepY = Math.max(1, Math.floor(h / 64));
  for (let y = 0; y < h; y += stepY) {
    for (let x = 0; x < w; x += stepX) {
      const alpha = ctx.getImageData(x, y, 1, 1).data[3];
      if (alpha !== undefined && alpha < 250) {
        return true;
      }
    }
  }
  return false;
}
