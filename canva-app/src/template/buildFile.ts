import type { Panel } from "./panels";
import type { ColorRole, FontRole } from "./roles";
import type { Extraction, Field, FixedText } from "./types";

export const FORMAT = "bettercricket-template";

type Look = {
  x: number;
  y: number;
  w: number;
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
  canvas: { w: number; h: number };
  background?: string;
  fields: (Look & { token: string })[];
  texts?: (Look & { text: string })[];
  panels?: {
    x: number;
    y: number;
    w: number;
    h: number;
    color?: string;
    source: Panel["source"];
  }[];
};

const lookOf = (f: Field | FixedText): Look => ({
  x: f.x,
  y: f.y,
  w: f.w,
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

/**
 * The file BetterCricket imports (spec: frontend/src/social/boundFields.js).
 * It carries the structure: where each field and fixed word sits, how big it is,
 * and which colour and font ROLE it uses, so the club's own palette and fonts fill
 * it in. The designer's own colour and font name are there too, for a club that
 * wants to keep the Canva look. `background` is optional: the design as a picture.
 */
export function buildTemplateFile(
  extraction: Extraction,
  opts: { name: string; background?: string },
): TemplateFile {
  return {
    format: FORMAT,
    version: 1,
    name: opts.name.trim() || "Canva template",
    canvas: extraction.canvas,
    ...(opts.background ? { background: opts.background } : null),
    fields: extraction.fields.map((f) => ({ token: f.token, ...lookOf(f) })),
    ...(extraction.panels.length
      ? {
          panels: extraction.panels.map((p) => ({
            x: p.x,
            y: p.y,
            w: p.w,
            h: p.h,
            ...(p.color ? { color: p.color } : null),
            source: p.source,
          })),
        }
      : null),
    ...(extraction.texts.length
      ? { texts: extraction.texts.map((t) => ({ text: t.text, ...lookOf(t) })) }
      : null),
  };
}
