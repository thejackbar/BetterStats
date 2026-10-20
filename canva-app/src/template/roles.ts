// Colours and fonts are carried as roles, not copies, so BetterCricket can fill
// them in from the club's own palette and fonts. The designer's exact values are
// still in the file (for "keep my Canva look"); the roles are what a club's
// branding then restyles.

export type ColorRole = "ink" | "accent";
export type FontRole = "display" | "body";

const HEX = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i;

/** Saturation and lightness (each 0 to 1) of a #rrggbb colour, or null if it is not one. */
export function hsl(hex: string): { s: number; l: number } | null {
  const m = hex.match(HEX);
  if (!m) {
    return null;
  }
  const [r, g, b] = [m[1], m[2], m[3]].map(
    (v) => parseInt(v ?? "0", 16) / 255,
  ) as [number, number, number];
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  return { s, l };
}

/**
 * White, near-black and greys are the text colour of the design, so they become
 * BetterCricket's ink (which suits whichever background the club uses). A
 * clearly coloured one is a highlight, so it becomes the club's accent.
 */
export function colorRole(hex: string | null): ColorRole {
  const c = hex ? hsl(hex) : null;
  if (!c) {
    return "ink";
  }
  const neutral = c.s < 0.2 || c.l > 0.92 || c.l < 0.1;
  return neutral ? "ink" : "accent";
}

/** Headings and large words use the club's display font; small body text its body font. */
export const DISPLAY_FROM = 56;

export function fontRole(bold: boolean, fontSize: number): FontRole {
  return bold || fontSize >= DISPLAY_FROM ? "display" : "body";
}
