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
  /** Covers (nearly) the whole page, so it is the background in effect. */
  fullPage: boolean;
  rotated: boolean;
};

const FULL = 0.95;

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
      const x = Math.round(offset.x + el.left);
      const y = Math.round(offset.y + el.top);
      const fullPage =
        !!dims &&
        el.width >= dims.width * FULL &&
        el.height >= dims.height * FULL;
      return {
        kind,
        x,
        y,
        w: Math.round(el.width),
        h: Math.round(el.height),
        fill,
        paths,
        fullPage,
        rotated: rotated || Math.abs(el.rotation) > 1,
      };
    },
  );
}
