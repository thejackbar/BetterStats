import { surfaceBoxes } from "./walk";
import type { FillLike, PageLike } from "./types";

export type SurfaceFill =
  | { kind: "solid"; color: string }
  | { kind: "image" }
  | { kind: "video" }
  | { kind: "mixed" }
  | { kind: "none" };

/** A non-text element on the page, in the page's own pixels. */
export type Surface = {
  kind: "rect" | "shape" | "other";
  x: number;
  y: number;
  w: number;
  h: number;
  fill: SurfaceFill;
  /** Vector paths in a shape; 0 for anything else. */
  paths: number;
  /** The element's own rotation in degrees (0 when upright). */
  rotation: number;
  /** Where it really sits on the page once rotated, in the page's own pixels. */
  visual: { x: number; y: number; w: number; h: number };
  /** Covers (nearly) the whole page, so it is the background in effect. */
  fullPage: boolean;
  /** In a rotated group, so its place cannot be worked out. */
  inRotatedGroup: boolean;
  /** Any rotation at all, for the list in the panel. */
  rotated: boolean;
  /** What the export does with it. Set once the page has been read as a whole. */
  use: "panel" | "background" | "left_out";
};

const FULL = 0.95;

/** The box an element covers once it is turned about its centre. */
export function visualBounds(
  x: number,
  y: number,
  w: number,
  h: number,
  rotation: number,
) {
  const t = (rotation * Math.PI) / 180;
  const c = Math.abs(Math.cos(t));
  const sn = Math.abs(Math.sin(t));
  const vw = w * c + h * sn;
  const vh = w * sn + h * c;
  const cx = x + w / 2;
  const cy = y + h / 2;
  return { x: cx - vw / 2, y: cy - vh / 2, w: vw, h: vh };
}

/** What one fill is: a colour, a picture, a video, or nothing. */
export function fillOf(fill: FillLike): SurfaceFill {
  const media = fill.mediaContainer.ref;
  if (media && (media.type === "image" || media.type === "video")) {
    return { kind: media.type };
  }
  const color = fill.colorContainer.ref;
  if (color && color.type === "solid") {
    return { kind: "solid", color: color.color.toLowerCase() };
  }
  return { kind: "none" };
}

const sameFill = (a: SurfaceFill, b: SurfaceFill): boolean =>
  a.kind === b.kind &&
  (a.kind !== "solid" || (b.kind === "solid" && a.color === b.color));

/**
 * Describes every rect, shape and other non-text element on the page, so a club
 * (and this app) can see how Canva sees a design: is a panel a vector shape with
 * a solid colour, or a picture? Reads only; changes nothing.
 */
export function describeSurfaces(page: PageLike): Surface[] {
  const dims = page.dimensions;
  return surfaceBoxes(page.elements.toArray()).map(
    ({ el, offset, rotated }) => {
      let kind: Surface["kind"] = "other";
      let fill: SurfaceFill = { kind: "none" };
      let paths = 0;
      if (el.type === "rect") {
        kind = "rect";
        fill = fillOf(el.fill);
      } else if (el.type === "shape") {
        kind = "shape";
        const list = el.paths.toArray();
        paths = list.length;
        const fills = list.map((p) => fillOf(p.fill));
        const first = fills[0];
        fill =
          first && fills.every((f) => sameFill(f, first))
            ? first
            : fills.length
              ? { kind: "mixed" }
              : { kind: "none" };
      }
      const x = offset.x + el.left;
      const y = offset.y + el.top;
      const visual = visualBounds(x, y, el.width, el.height, el.rotation);
      // Covers the whole page once the part off the page is cut away.
      const fullPage =
        !!dims &&
        Math.min(visual.x + visual.w, dims.width) - Math.max(visual.x, 0) >=
          dims.width * FULL &&
        Math.min(visual.y + visual.h, dims.height) - Math.max(visual.y, 0) >=
          dims.height * FULL;
      return {
        kind,
        x: Math.round(x),
        y: Math.round(y),
        w: Math.round(el.width),
        h: Math.round(el.height),
        fill,
        paths,
        rotation: Math.round(el.rotation),
        visual,
        fullPage,
        inRotatedGroup: rotated,
        rotated: rotated || Math.abs(el.rotation) > 1,
        use: "left_out" as const,
      };
    },
  );
}
