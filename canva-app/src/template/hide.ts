import { tokenBoxes } from "./walk";
import type { PageLike } from "./types";

/** A field box that was hidden for the export, with what it was before. */
export type Hidden = {
  token: string;
  /** Place on the page, with any groups' positions added in. */
  x: number;
  y: number;
  /** The box's own transparency before it was hidden (0 to 1). */
  original: number;
};

const SAME = 0.5;

/**
 * Hides every field box (a text box holding exactly one {{token}}) by making it
 * fully transparent, so the exported picture has the design without the words
 * BetterCricket will draw itself. Returns what it changed so it can be undone.
 * Locked boxes and boxes in a rotated group are left alone (extractFields
 * reports them, and the export refuses to go ahead while any exist).
 */
export function hideFields(page: PageLike): Hidden[] {
  const hidden: Hidden[] = [];
  for (const box of tokenBoxes(page.elements.toArray())) {
    if (box.token == null || box.locked || box.rotated) {
      continue;
    }
    hidden.push({
      token: box.token,
      x: box.offset.x + box.el.left,
      y: box.offset.y + box.el.top,
      original: box.el.transparency,
    });
    box.el.transparency = 1;
  }
  return hidden;
}

/**
 * Puts hidden boxes back to the transparency they had. Each is found again by its
 * token and place (hiding moves nothing). `missing` counts boxes that are no longer
 * there, for example because they were deleted in between.
 */
export function restoreFields(
  page: PageLike,
  hidden: readonly Hidden[],
): { restored: number; missing: number } {
  const boxes = tokenBoxes(page.elements.toArray());
  const used = new Set<number>();
  let restored = 0;
  for (const h of hidden) {
    const i = boxes.findIndex(
      (b, idx) =>
        !used.has(idx) &&
        b.token === h.token &&
        Math.abs(b.offset.x + b.el.left - h.x) < SAME &&
        Math.abs(b.offset.y + b.el.top - h.y) < SAME,
    );
    const box = i >= 0 ? boxes[i] : undefined;
    if (box) {
      used.add(i);
      box.el.transparency = h.original;
      restored++;
    }
  }
  return { restored, missing: hidden.length - restored };
}
