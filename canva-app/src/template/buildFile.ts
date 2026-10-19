import type { Extraction } from "./types";

export const FORMAT = "bettercricket-template";

export type TemplateFile = {
  format: typeof FORMAT;
  version: 1;
  name: string;
  canvas: { w: number; h: number };
  background?: string;
  fields: {
    token: string;
    x: number;
    y: number;
    w: number;
    fontFamily?: string;
    fontSize: number;
    bold: boolean;
    color?: string;
    align: "left" | "center" | "right";
    uppercase: boolean;
    lineHeight: number;
    letterSpacing: number;
  }[];
};

/**
 * The file BetterCricket imports (spec: frontend/src/social/boundFields.js).
 * `background` is the design with the field words taken out, as a data URL.
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
    fields: extraction.fields.map((f) => ({
      token: f.token,
      x: f.x,
      y: f.y,
      w: f.w,
      ...(f.fontFamily ? { fontFamily: f.fontFamily } : null),
      fontSize: f.fontSize,
      bold: f.bold,
      ...(f.color ? { color: f.color } : null),
      align: f.align,
      uppercase: f.uppercase,
      lineHeight: 1,
      letterSpacing: 0,
    })),
  };
}
