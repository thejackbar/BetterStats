import type { Panel } from "./panels";
import type { ColorRole, FontRole } from "./roles";
import type { Extraction, Field, FixedText } from "./types";

export const FORMAT = "bettercricket-template";

/** Where BetterCricket imports it: the Lineup layout, or the Blank canvas. */
export type PostType = "lineup" | "general";

type Look = {
  x: number;
  y: number;
  w: number;
  /** Only for a photo or sponsors area. */
  h?: number;
  fontFamily?: string;
  fontSize: number;
  bold: boolean;
  color?: string;
  colorRole: ColorRole;
  fontRole: FontRole;
  align: "left" | "center" | "right";
  uppercase: boolean;
  lineHeight: number;
  letterSpacing: number;
};

export type TemplateFile = {
  format: typeof FORMAT;
  version: 1;
  name: string;
  postType: PostType;
  canvas: { w: number; h: number };
  background?: string;
  fields: (Look & { token: string })[];
  texts?: (Look & { text: string })[];
  /** Pictures nothing is written on, each with its own box (before it was turned). */
  pictures?: { image: string; box: NonNullable<Panel["box"]> }[];
  panels?: {
    x: number;
    y: number;
    w: number;
    h: number;
    color?: string;
    source: Panel["source"];
    /** The panel's own picture (a data URL) and its rectangle before it was turned. */
    image?: string;
    box?: NonNullable<Panel["box"]>;
  }[];
};

const lookOf = (f: Field | FixedText): Look => ({
  x: f.x,
  y: f.y,
  w: f.w,
  ...("h" in f && f.h ? { h: f.h } : null),
  ...(f.fontFamily ? { fontFamily: f.fontFamily } : null),
  fontSize: f.fontSize,
  bold: f.bold,
  ...(f.color ? { color: f.color } : null),
  colorRole: f.colorRole,
  fontRole: f.fontRole,
  align: f.align,
  uppercase: f.uppercase,
  lineHeight: 1,
  letterSpacing: 0,
});

export type Pictures = {
  background?: string;
  /** Data URLs by Canva image id. */
  byRef: ReadonlyMap<string, string>;
};

/** The free-standing pictures that could be fetched, with their data and box. */
function pictureList(extraction: Extraction, pictures?: Pictures) {
  const out: { image: string; box: NonNullable<Panel["box"]> }[] = [];
  for (const p of extraction.pictures) {
    const image = pictures?.byRef.get(p.imageRef);
    if (image) {
      out.push({ image, box: p.box });
    }
  }
  return out;
}

/**
 * The file BetterCricket imports (spec: frontend/src/social/boundFields.js).
 * It carries the structure: where each field and fixed word sits, how big it is,
 * and which colour and font ROLE it uses, so the club's own palette and fonts fill
 * it in. The designer's own colour and font name are there too, for a club that
 * wants to keep the Canva look. The design's own pictures (its background and the pictures panels are filled with) ride along when they could be fetched.
 */
export function buildTemplateFile(
  extraction: Extraction,
  opts: { name: string; postType: PostType; pictures?: Pictures },
): TemplateFile {
  return {
    format: FORMAT,
    version: 1,
    name: opts.name.trim() || "Canva template",
    postType: opts.postType,
    canvas: extraction.canvas,
    ...(opts.pictures?.background
      ? { background: opts.pictures.background }
      : null),
    fields: extraction.fields.map((f) => ({ token: f.token, ...lookOf(f) })),
    ...(extraction.panels.length
      ? {
          panels: extraction.panels.map((p) => {
            const image = p.imageRef
              ? opts.pictures?.byRef.get(p.imageRef)
              : undefined;
            return {
              x: p.x,
              y: p.y,
              w: p.w,
              h: p.h,
              ...(p.color ? { color: p.color } : null),
              source: p.source,
              ...(image && p.box ? { image, box: p.box } : null),
            };
          }),
        }
      : null),
    ...(pictureList(extraction, opts.pictures).length
      ? { pictures: pictureList(extraction, opts.pictures) }
      : null),
    ...(extraction.texts.length
      ? { texts: extraction.texts.map((t) => ({ text: t.text, ...lookOf(t) })) }
      : null),
  };
}
