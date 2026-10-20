import type { Surface } from "./describe";

/** A surface behind text: BetterCricket draws its own in the same place. */
export type Panel = {
  x: number;
  y: number;
  w: number;
  h: number;
  /** The designer's colour when the surface is a solid fill, else null (a picture). */
  color: string | null;
  source: "solid" | "picture" | "shape";
  /** Canva's id for the panel's own picture, when it is filled with one. */
  imageRef: string | null;
  /**
   * Where that picture really sits, before it was turned (BetterPosts draws the
   * picture in its own box and turns it): not cut to the page, in the 1080 space.
   */
  box: { x: number; y: number; w: number; h: number; rotation: number } | null;
};

/** A box of text on the page, in the page's own pixels, and how it is aligned. */
export type Anchor = {
  x: number;
  y: number;
  w: number;
  h: number;
  align: "left" | "center" | "right";
};

// A text box is often wider than the words in it, so where the words sit depends
// on the alignment: at the left edge, the middle, or the right edge.
const INSET = 8;

const MAX_PANELS = 6;
const MIN_SHARE = 0.05;
const OVERLAP = 0.8;

type Rect = { x: number; y: number; w: number; h: number };

const area = (r: Rect) => r.w * r.h;

const intersection = (a: Rect, b: Rect): Rect | null => {
  const x = Math.max(a.x, b.x);
  const y = Math.max(a.y, b.y);
  const w = Math.min(a.x + a.w, b.x + b.w) - x;
  const h = Math.min(a.y + a.h, b.y + b.h) - y;
  return w > 0 && h > 0 ? { x, y, w, h } : null;
};

/** Where the words of a text box are, for deciding what they sit on. */
export const wordsPoint = (a: Anchor) => ({
  x:
    a.align === "left"
      ? a.x + Math.min(INSET, a.w / 2)
      : a.align === "right"
        ? a.x + a.w - Math.min(INSET, a.w / 2)
        : a.x + a.w / 2,
  y: a.y + a.h / 2,
});

const sitsOn = (a: Anchor, r: Rect) => {
  const p = wordsPoint(a);
  return p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;
};

/**
 * Finds the surfaces that sit behind text, which BetterCricket redraws as panels
 * in the club's colours: a rectangle, shape or picture that is not the whole page
 * and has at least one text box inside it. A surface covering the whole page is
 * the background (BetterCricket draws its own). Anything else is left out, and
 * said so. Returns the panels in BetterPosts' 1080 wide space, and the surfaces
 * marked with what became of each.
 */
export function findPanels(
  surfaces: readonly Surface[],
  anchors: readonly Anchor[],
  page: { width: number; height: number },
  scale: number,
): { panels: Panel[]; surfaces: Surface[] } {
  const pageRect: Rect = { x: 0, y: 0, w: page.width, h: page.height };
  const candidates: { index: number; rect: Rect }[] = [];

  const marked: Surface[] = surfaces.map((sf, index) => {
    // Already taken as a photo or sponsors area: not a panel.
    if (sf.use === "area") {
      return sf;
    }
    if (sf.fullPage) {
      return { ...sf, use: "background" as const };
    }
    if (
      sf.inRotatedGroup ||
      sf.kind === "other" ||
      sf.fill.kind === "video" ||
      sf.fill.kind === "none"
    ) {
      return { ...sf, use: "left_out" as const };
    }
    // Only the part that is on the page counts.
    const rect = intersection(sf.visual, pageRect);
    if (
      !rect ||
      rect.w < page.width * MIN_SHARE ||
      rect.h < page.height * MIN_SHARE
    ) {
      return { ...sf, use: "left_out" as const };
    }
    if (!anchors.some((a) => sitsOn(a, rect))) {
      return { ...sf, use: "left_out" as const };
    }
    candidates.push({ index, rect });
    return { ...sf, use: "panel" as const };
  });

  // Two surfaces covering nearly the same place are one panel: keep the larger.
  const kept = candidates
    .slice()
    .sort((a, b) => area(b.rect) - area(a.rect))
    .filter((c, i, all) => {
      for (const bigger of all.slice(0, i)) {
        const both = intersection(c.rect, bigger.rect);
        if (both && area(both) / area(c.rect) >= OVERLAP) {
          marked[c.index] = { ...must(marked[c.index]), use: "left_out" };
          return false;
        }
      }
      return true;
    })
    .slice(0, MAX_PANELS);
  const keptIndexes = new Set(kept.map((c) => c.index));
  for (const c of candidates) {
    if (!keptIndexes.has(c.index)) {
      marked[c.index] = { ...must(marked[c.index]), use: "left_out" };
    }
  }

  const panels = kept.map(({ index, rect }): Panel => {
    const sf = must(surfaces[index]);
    // Round the edges, then take the size from them, so a panel that reaches the
    // edge of the page ends exactly on it.
    const x0 = Math.round(rect.x * scale);
    const y0 = Math.round(rect.y * scale);
    const x1 = Math.round((rect.x + rect.w) * scale);
    const y1 = Math.round((rect.y + rect.h) * scale);
    return {
      x: x0,
      y: y0,
      w: x1 - x0,
      h: y1 - y0,
      color: sf.fill.kind === "solid" ? sf.fill.color : null,
      source:
        sf.fill.kind === "solid"
          ? "solid"
          : sf.kind === "shape"
            ? "shape"
            : "picture",
      imageRef: sf.fill.kind === "image" ? sf.fill.imageRef : null,
      box:
        sf.fill.kind === "image" && sf.fill.imageRef
          ? {
              x: Math.round(sf.x * scale),
              y: Math.round(sf.y * scale),
              w: Math.round(sf.w * scale),
              h: Math.round(sf.h * scale),
              rotation: sf.rotation,
            }
          : null,
    };
  });
  return { panels, surfaces: marked };
}

function must<T>(v: T | undefined): T {
  if (v === undefined) {
    throw new Error("Expected a surface.");
  }
  return v;
}
