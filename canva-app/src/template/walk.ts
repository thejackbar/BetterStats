import { hasToken, wholeToken } from "./tokens";
import type {
  ElementLike,
  OtherElementLike,
  RectElementLike,
  ShapeElementLike,
  TextElementLike,
} from "./types";

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

/** Every text box at any depth, token or not. */
export type TextBox = TokenBox & { hasToken: boolean };

/**
 * Every text box holding a {{ }}, at any depth. A box inside a group is
 * positioned relative to the group, so the groups' own positions are carried
 * along as `offset`.
 */
export function tokenBoxes(elements: readonly ElementLike[]): TokenBox[] {
  return textBoxes(elements).filter((b) => b.hasToken);
}

/** All text boxes, with the same context, so fixed words can be read too. */
export function textBoxes(elements: readonly ElementLike[]): TextBox[] {
  const out: TextBox[] = [];
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
        out.push({
          el,
          text,
          hasToken: hasToken(text),
          token: wholeToken(text),
          offset,
          locked: locked || el.locked,
          rotated,
        });
      }
    }
  };
  scan(elements, { x: 0, y: 0 }, false, false);
  return out;
}

/** A rect, shape or other non-text element, and where it sits. */
export type SurfaceBox = {
  el: RectElementLike | ShapeElementLike | OtherElementLike;
  offset: { x: number; y: number };
  rotated: boolean;
};

/** Every non-text element at any depth, with its groups' positions carried along. */
export function surfaceBoxes(elements: readonly ElementLike[]): SurfaceBox[] {
  const out: SurfaceBox[] = [];
  const scan = (
    list: readonly ElementLike[],
    offset: { x: number; y: number },
    rotated: boolean,
  ) => {
    for (const el of list) {
      if (el.type === "group") {
        scan(
          el.contents.toArray(),
          { x: offset.x + el.left, y: offset.y + el.top },
          rotated || Math.abs(el.rotation) > 1,
        );
      } else if (el.type !== "text") {
        out.push({ el, offset, rotated });
      }
    }
  };
  scan(elements, { x: 0, y: 0 }, false);
  return out;
}
