import { hasToken, wholeToken } from "./tokens";
import type { ElementLike, TextElementLike } from "./types";

/** A text box with a {{token}} in it, and where it sits. */
export type TokenBox = {
  el: TextElementLike;
  text: string;
  /** The word inside {{ }} when the whole text is one token, else null. */
  token: string | null;
  /** The summed top and left of every group around the box. */
  offset: { x: number; y: number };
  /** The box, or a group around it, is locked. */
  locked: boolean;
  /** A group around the box is rotated, so its place cannot be worked out. */
  rotated: boolean;
};

/**
 * Every text box holding a {{ }}, at any depth. A box inside a group is
 * positioned relative to the group, so the groups' own positions are carried
 * along as `offset`.
 */
export function tokenBoxes(elements: readonly ElementLike[]): TokenBox[] {
  const out: TokenBox[] = [];
  const scan = (
    list: readonly ElementLike[],
    offset: { x: number; y: number },
    locked: boolean,
    rotated: boolean,
  ) => {
    for (const el of list) {
      if (el.type === "group") {
        scan(
          el.contents.toArray(),
          { x: offset.x + el.left, y: offset.y + el.top },
          locked || el.locked,
          rotated || Math.abs(el.rotation) > 1,
        );
      } else if (el.type === "text") {
        const text = el.text.readPlaintext();
        if (hasToken(text)) {
          out.push({
            el,
            text,
            token: wholeToken(text),
            offset,
            locked: locked || el.locked,
            rotated,
          });
        }
      }
    }
  };
  scan(elements, { x: 0, y: 0 }, false, false);
  return out;
}
