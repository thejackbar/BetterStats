// Ready-made blocks the app drops into a design: text boxes already holding the
// right {{tokens}}, laid out to fit the page. Pure layout only; insert.ts puts
// them into Canva.

export type BoxSpec = {
  text: string;
  top: number;
  left: number;
  width: number;
  fontSize: number;
  bold: boolean;
  color: string;
  align: "start" | "center" | "end";
};

export type BlockSpec = { name: string; boxes: BoxSpec[] };

export type PageSize = { width: number; height: number };

export const MAX_LINEUP = 15;
const INK = "#222222";

const clamp = (n: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, n));

/**
 * A heading and one {{player N}} box per place, evenly down the left of the page.
 * Rows share the height, so eleven or fifteen both fit; the type size follows.
 */
export function lineUpBlock(
  page: PageSize,
  count: number,
  heading = true,
): BlockSpec {
  const n = clamp(Math.round(count) || 1, 1, MAX_LINEUP);
  const margin = Math.round(page.width * 0.08);
  const topMargin = Math.round(page.height * 0.08);
  const width = Math.round(page.width * 0.5);
  const headingRows = heading ? 1.6 : 0;
  const rowH = (page.height * 0.84) / (n + headingRows);
  const fontSize = clamp(
    Math.floor(rowH / 1.4),
    10,
    Math.floor(page.height * 0.06),
  );
  const boxes: BoxSpec[] = [];
  if (heading) {
    boxes.push({
      text: "LINE UP",
      top: topMargin,
      left: margin,
      width,
      fontSize: Math.round(fontSize * 1.2),
      bold: true,
      color: INK,
      align: "start",
    });
  }
  for (let i = 0; i < n; i++) {
    boxes.push({
      text: `{{player ${i + 1}}}`,
      top: Math.round(topMargin + headingRows * rowH + i * rowH),
      left: margin,
      width,
      fontSize,
      bold: false,
      color: INK,
      align: "start",
    });
  }
  return { name: "Line up", boxes };
}

const DETAILS = ["opponent", "date", "time", "venue", "competition", "round"];

/** The match details a post usually carries, stacked down the right of the page. */
export function matchDetailsBlock(page: PageSize): BlockSpec {
  const left = Math.round(page.width * 0.62);
  const width = Math.round(page.width * 0.3);
  const topMargin = Math.round(page.height * 0.08);
  const fontSize = clamp(
    Math.round(page.height * 0.035),
    10,
    Math.floor(page.height * 0.06),
  );
  const rowH = fontSize * 1.8;
  return {
    name: "Match details",
    boxes: DETAILS.map((d, i) => ({
      text: `{{${d}}}`,
      top: Math.round(topMargin + i * rowH),
      left,
      width,
      fontSize,
      bold: false,
      color: INK,
      align: "start" as const,
    })),
  };
}
