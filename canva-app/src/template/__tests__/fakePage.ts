import type {
  ElementLike,
  FormatLike,
  GroupElementLike,
  PageLike,
  TextElementLike,
} from "../types";

export function textBox(
  text: string,
  o: Partial<{
    top: number;
    left: number;
    width: number;
    height: number;
    rotation: number;
    transparency: number;
    locked: boolean;
    format: FormatLike;
  }> = {},
): TextElementLike {
  return {
    type: "text",
    locked: o.locked ?? false,
    width: o.width ?? 400,
    height: o.height ?? 60,
    top: o.top ?? 0,
    left: o.left ?? 0,
    rotation: o.rotation ?? 0,
    transparency: o.transparency ?? 0,
    text: {
      readPlaintext: () => text,
      readTextRegions: () => [{ text, formatting: o.format }],
    },
  };
}

export const group = (...contents: ElementLike[]): GroupElementLike => ({
  type: "group",
  contents: { toArray: () => contents },
});

export const page = (
  elements: ElementLike[],
  dimensions: { width: number; height: number } | undefined = {
    width: 1080,
    height: 1080,
  },
): PageLike => ({
  type: "absolute",
  dimensions,
  elements: { toArray: () => elements },
});
