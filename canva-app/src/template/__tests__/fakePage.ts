import type {
  ElementLike,
  FillLike,
  FillRefLike,
  RectElementLike,
  ShapeElementLike,
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

export const group = (
  contents: ElementLike[],
  o: Partial<{
    top: number;
    left: number;
    rotation: number;
    locked: boolean;
  }> = {},
): GroupElementLike => ({
  type: "group",
  locked: o.locked ?? false,
  top: o.top ?? 0,
  left: o.left ?? 0,
  rotation: o.rotation ?? 0,
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

/** Narrows a value a test knows is there, failing loudly when it is not. */
export function must<T>(value: T | undefined | null): T {
  if (value == null) {
    throw new Error("Expected a value in the test, found none.");
  }
  return value;
}

const fillOf = (colour?: string, media?: "image" | "video"): FillLike => ({
  colorContainer: {
    ref: colour ? { type: "solid", color: colour } : undefined,
  },
  mediaContainer: {
    ref: media ? ({ type: media } as FillRefLike) : undefined,
  },
});

type BoxOpts = Partial<{
  top: number;
  left: number;
  width: number;
  height: number;
  rotation: number;
  transparency: number;
  locked: boolean;
}>;

const box = (o: BoxOpts) => ({
  top: o.top ?? 0,
  left: o.left ?? 0,
  width: o.width ?? 100,
  height: o.height ?? 100,
  rotation: o.rotation ?? 0,
  transparency: o.transparency ?? 0,
  locked: o.locked ?? false,
});

export const rect = (
  o: BoxOpts & { colour?: string; media?: "image" | "video" } = {},
): RectElementLike => ({
  type: "rect",
  ...box(o),
  fill: fillOf(o.colour, o.media),
});

export const shape = (
  o: BoxOpts & {
    paths?: { d: string; colour?: string; media?: "image" | "video" }[];
  } = {},
): ShapeElementLike => ({
  type: "shape",
  ...box(o),
  paths: {
    toArray: () =>
      (o.paths ?? [{ d: "M0 0H10V10Z", colour: "#000000" }]).map((p) => ({
        d: p.d,
        fill: fillOf(p.colour, p.media),
      })),
  },
});
