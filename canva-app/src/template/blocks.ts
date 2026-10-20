import { bindFromToken, bindLabel } from "./tokens";

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

/** A plain rectangle that marks an area (a photo, the sponsors). Drawn under the text. */
export type RectSpec = {
  top: number;
  left: number;
  width: number;
  height: number;
  color: string;
  transparency: number;
};

export type BlockSpec = { name: string; boxes: BoxSpec[]; rects?: RectSpec[] };

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

const AREA = "#9aa0a6";

/** A rectangle marking an area, with its field word sitting centred inside it. */
function areaBlock(
  name: string,
  token: string,
  rect: { top: number; left: number; width: number; height: number },
  fontSize: number,
): BlockSpec {
  return {
    name,
    rects: [{ ...rect, color: AREA, transparency: 0.55 }],
    boxes: [
      {
        text: `{{${token}}}`,
        top: Math.round(rect.top + (rect.height - fontSize * 1.3) / 2),
        left: rect.left,
        width: rect.width,
        fontSize,
        bold: false,
        color: INK,
        align: "center",
      },
    ],
  };
}

/**
 * A strip for the club's sponsors. The grey rectangle is only a marker: its size and
 * place are the sponsors area in BetterCricket, which fills it with the post's logos.
 */
export function sponsorsBlock(page: PageSize): BlockSpec {
  const fontSize = clamp(Math.round(page.height * 0.022), 10, 40);
  return areaBlock(
    "Sponsors box",
    "sponsors",
    {
      top: Math.round(page.height * 0.86),
      left: Math.round(page.width * 0.08),
      width: Math.round(page.width * 0.84),
      height: Math.round(page.height * 0.1),
    },
    fontSize,
  );
}

/** What a player can carry besides a name, as the picker lists it. */
export const PLAYER_EXTRAS = [
  "photo",
  "captain",
  "vice captain",
  "keeper",
  "debut",
] as const;

/**
 * The photo area for one player, or a small box that prints their captain,
 * vice-captain, keeper or debut mark (BetterCricket prints it only for the players who are).
 */
export function playerExtraBlock(
  page: PageSize,
  place: number,
  extra: string,
  slot = 0,
): BlockSpec {
  const token = `player ${place} ${extra}`;
  const name = bindLabel(bindFromToken(token) ?? token);
  if (extra === "photo") {
    const side = Math.round(page.width * 0.16);
    return areaBlock(
      name,
      token,
      {
        top: Math.round(page.height * 0.1 + (slot % 4) * side * 0.15),
        left: Math.round(page.width * 0.62 + (slot % 4) * side * 0.15),
        width: side,
        height: side,
      },
      clamp(Math.round(page.height * 0.02), 10, 40),
    );
  }
  return {
    ...fieldBlock(page, token, slot),
    name,
  };
}

/** Every field a single box can hold, in the order the picker lists them. */
export const FIELD_TOKENS: string[] = [
  ...Array.from({ length: MAX_LINEUP }, (_, i) => `player ${i + 1}`),
  "captain",
  "keeper",
  "opponent",
  "team",
  "headline",
  "competition",
  "round",
  "date",
  "time",
  "venue",
  "season",
];

/**
 * One box holding one field, for a club that wants to place each piece itself.
 * `slot` steps each new box down a little so boxes added in a row do not sit
 * exactly on top of each other.
 */
export function fieldBlock(page: PageSize, token: string, slot = 0): BlockSpec {
  const fontSize = clamp(
    Math.round(page.height * 0.04),
    10,
    Math.floor(page.height * 0.06),
  );
  return {
    name: bindLabel(bindFromToken(token) ?? token),
    boxes: [
      {
        text: `{{${token}}}`,
        top: Math.round(page.height * 0.4 + (slot % 8) * fontSize * 1.6),
        left: Math.round(page.width * 0.08),
        width: Math.round(page.width * 0.5),
        fontSize,
        bold: false,
        color: INK,
        align: "start",
      },
    ],
  };
}
