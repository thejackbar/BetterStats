import {
  INK,
  areaBlock,
  clamp,
  type BlockSpec,
  type BoxSpec,
  type PageSize,
} from "./blocks";
import type { PostType } from "./postFields";

// Ready-made blocks for the post types other than the line up. Each one is text
// boxes already holding the right {{words}} (see postFields.ts), laid out to fit the
// page, so a club builds the design around them. Pure layout only; insert.ts puts them
// into Canva.

export type BlockId =
  | "fixturesList"
  | "resultsList"
  | "finalScore"
  | "performers"
  | "potm"
  | "stats"
  | "team"
  | "milestoneList"
  | "announce"
  | "toss"
  | "eventDetails"
  | "eventList";

export type TypeBlock = {
  id: BlockId;
  /** A block that repeats a row: how many rows the club can ask for. */
  count?: { min: number; max: number; start: number };
  build: (page: PageSize, count: number) => BlockSpec;
};

type Col = {
  token: (n: number) => string;
  share: number;
  align?: BoxSpec["align"];
  bold?: boolean;
};

type Region = { top: number; height: number };

const margins = (page: PageSize) => ({
  left: Math.round(page.width * 0.08),
  width: Math.round(page.width * 0.84),
  top: Math.round(page.height * 0.08),
});

/**
 * Rows of columns, one text box per cell, with an optional heading above. The rows
 * share the region's height, so two rows or eight both fit, and the type size follows.
 */
function rowsBlock(
  name: string,
  page: PageSize,
  count: number,
  cols: Col[],
  opts: { heading?: string; region?: Region } = {},
): BlockSpec {
  const m = margins(page);
  const region = opts.region ?? {
    top: m.top,
    height: Math.round(page.height * 0.84),
  };
  const headingRows = opts.heading ? 1.6 : 0;
  const rowH = region.height / (count + headingRows);
  const fontSize = clamp(
    Math.floor(rowH / 1.4),
    10,
    Math.floor(page.height * 0.05),
  );
  const boxes: BoxSpec[] = [];
  if (opts.heading) {
    boxes.push({
      text: opts.heading,
      top: region.top,
      left: m.left,
      width: m.width,
      fontSize: Math.round(fontSize * 1.2),
      bold: true,
      color: INK,
      align: "start",
    });
  }
  const gap = Math.round(page.width * 0.01);
  for (let i = 0; i < count; i++) {
    let x = m.left;
    for (const col of cols) {
      const w = Math.round(m.width * col.share);
      boxes.push({
        text: `{{${col.token(i + 1)}}}`,
        top: Math.round(region.top + headingRows * rowH + i * rowH),
        left: x,
        width: Math.max(20, w - gap),
        fontSize,
        bold: !!col.bold,
        color: INK,
        align: col.align ?? "start",
      });
      x += w;
    }
  }
  return { name, boxes };
}

type Line = { text: string; scale: number; bold?: boolean };

/** Lines stacked down the page, each sized relative to a base, in the left part or all across. */
function stackBlock(
  name: string,
  page: PageSize,
  lines: Line[],
  opts: { width?: number; align?: BoxSpec["align"]; top?: number } = {},
): BlockSpec {
  const m = margins(page);
  const base = clamp(Math.round(page.height * 0.04), 10, 60);
  const width = opts.width ?? m.width;
  let y = opts.top ?? m.top;
  const boxes: BoxSpec[] = lines.map((l) => {
    const fontSize = clamp(
      Math.round(base * l.scale),
      10,
      Math.floor(page.height * 0.25),
    );
    const box: BoxSpec = {
      text: l.text,
      top: Math.round(y),
      left: m.left,
      width,
      fontSize,
      bold: !!l.bold,
      color: INK,
      align: opts.align ?? "start",
    };
    y += fontSize * 1.45;
    return box;
  });
  return { name, boxes };
}

const merge = (name: string, ...parts: BlockSpec[]): BlockSpec => ({
  name,
  boxes: parts.flatMap((p) => p.boxes),
  rects: parts.flatMap((p) => p.rects ?? []),
});

const word = (t: string) => `{{${t}}}`;

/** A square photo area on the right, for the player a post is about. */
function photoArea(page: PageSize, token: string, label: string): BlockSpec {
  const side = Math.round(page.width * 0.3);
  return areaBlock(
    label,
    token,
    {
      top: Math.round(page.height * 0.3),
      left: Math.round(page.width * 0.62),
      width: side,
      height: Math.round(side * 1.2),
    },
    clamp(Math.round(page.height * 0.02), 10, 40),
  );
}

const fixturesList: TypeBlock = {
  id: "fixturesList",
  count: { min: 1, max: 8, start: 6 },
  build: (page, n) =>
    rowsBlock(
      "Fixtures list",
      page,
      n,
      [
        { token: (i) => `fixture ${i} grade`, share: 0.18, bold: true },
        { token: (i) => `fixture ${i} opponent`, share: 0.36 },
        { token: (i) => `fixture ${i} time`, share: 0.16 },
        { token: (i) => `fixture ${i} venue`, share: 0.3 },
      ],
      { heading: "FIXTURES" },
    ),
};

const resultsList: TypeBlock = {
  id: "resultsList",
  count: { min: 1, max: 8, start: 6 },
  build: (page, n) =>
    rowsBlock(
      "Results list",
      page,
      n,
      [
        { token: (i) => `result ${i} grade`, share: 0.18, bold: true },
        { token: (i) => `result ${i} opponent`, share: 0.34 },
        { token: (i) => `result ${i} our score`, share: 0.17 },
        { token: (i) => `result ${i} their score`, share: 0.17 },
        { token: (i) => `result ${i} outcome`, share: 0.14, bold: true },
      ],
      { heading: "RESULTS" },
    ),
};

const finalScore: TypeBlock = {
  id: "finalScore",
  build: (page) =>
    stackBlock(
      "Final score",
      page,
      [
        { text: word("team"), scale: 0.8 },
        { text: word("our score"), scale: 3, bold: true },
        { text: word("opponent"), scale: 0.8 },
        { text: word("opponent score"), scale: 3, bold: true },
        { text: word("result"), scale: 1.6, bold: true },
        { text: word("margin"), scale: 1 },
      ],
      { align: "center" },
    ),
};

const performers: TypeBlock = {
  id: "performers",
  count: { min: 1, max: 3, start: 2 },
  build: (page, n) => {
    const m = margins(page);
    const half = Math.round(page.height * 0.2);
    const side = (kind: "batter" | "bowler", top: number): BlockSpec =>
      rowsBlock(
        "Top performers",
        page,
        n,
        [
          { token: (i) => `our ${kind} ${i} name`, share: 0.29 },
          { token: (i) => `our ${kind} ${i} line`, share: 0.21, bold: true },
          { token: (i) => `opponent ${kind} ${i} name`, share: 0.29 },
          {
            token: (i) => `opponent ${kind} ${i} line`,
            share: 0.21,
            bold: true,
          },
        ],
        { region: { top, height: half } },
      );
    const first = Math.round(page.height * 0.55);
    return merge(
      "Top performers",
      side("batter", first),
      side("bowler", first + half + Math.round(m.top / 2)),
    );
  },
};

const potm: TypeBlock = {
  id: "potm",
  build: (page) =>
    merge(
      "Player of the match",
      stackBlock(
        "Player of the match",
        page,
        [
          { text: word("potm name"), scale: 1.8, bold: true },
          { text: word("potm line"), scale: 1 },
        ],
        { width: Math.round(page.width * 0.5) },
      ),
      photoArea(page, "potm photo", "Player of the match photo"),
    ),
};

const stats: TypeBlock = {
  id: "stats",
  count: { min: 1, max: 6, start: 3 },
  build: (page, n) =>
    rowsBlock(
      "Stats",
      page,
      n,
      [
        { token: (i) => `stat ${i} value`, share: 0.25, bold: true },
        { token: (i) => `stat ${i} label`, share: 0.5 },
      ],
      {
        region: {
          top: Math.round(page.height * 0.5),
          height: Math.round(page.height * 0.3),
        },
      },
    ),
};

const team: TypeBlock = {
  id: "team",
  count: { min: 1, max: 15, start: 11 },
  build: (page, n) =>
    rowsBlock(
      "Team of the week",
      page,
      n,
      [
        { token: (i) => `totw ${i} name`, share: 0.5, bold: true },
        { token: (i) => `totw ${i} line`, share: 0.5 },
      ],
      { heading: "TEAM OF THE WEEK" },
    ),
};

const milestoneList: TypeBlock = {
  id: "milestoneList",
  count: { min: 1, max: 8, start: 4 },
  build: (page, n) =>
    rowsBlock(
      "Milestones",
      page,
      n,
      [
        { token: (i) => `milestone ${i} name`, share: 0.4 },
        { token: (i) => `milestone ${i} value`, share: 0.15, bold: true },
        { token: (i) => `milestone ${i} unit`, share: 0.25 },
        { token: (i) => `milestone ${i} date`, share: 0.2 },
      ],
      { heading: word("milestone title") },
    ),
};

const announce: TypeBlock = {
  id: "announce",
  build: (page) =>
    merge(
      "Announcement",
      stackBlock(
        "Announcement",
        page,
        [
          { text: word("announcement kind"), scale: 0.8 },
          { text: word("announcement headline"), scale: 2.4, bold: true },
          { text: word("announcement subheadline"), scale: 1 },
          { text: word("announcement name"), scale: 1.6, bold: true },
        ],
        { width: Math.round(page.width * 0.5) },
      ),
      photoArea(page, "announcement photo", "Announcement photo"),
    ),
};

const toss: TypeBlock = {
  id: "toss",
  build: (page) =>
    stackBlock(
      "Toss",
      page,
      [
        { text: word("toss"), scale: 1.4, bold: true },
        { text: word("toss decision"), scale: 4, bold: true },
      ],
      { align: "center", top: Math.round(page.height * 0.3) },
    ),
};

const eventDetails: TypeBlock = {
  id: "eventDetails",
  build: (page) =>
    stackBlock("Event details", page, [
      { text: word("event kicker"), scale: 0.8 },
      { text: word("event title"), scale: 2.6, bold: true },
      { text: word("event subtitle"), scale: 1 },
      { text: word("event date"), scale: 1.4, bold: true },
      { text: word("event time"), scale: 1 },
      { text: word("event venue"), scale: 1 },
      { text: word("event price"), scale: 1 },
      { text: word("event cta"), scale: 1.2, bold: true },
    ]),
};

const eventList: TypeBlock = {
  id: "eventList",
  count: { min: 1, max: 8, start: 4 },
  build: (page, n) =>
    rowsBlock(
      "Dated list",
      page,
      n,
      [
        { token: (i) => `event item ${i} title`, share: 0.38, bold: true },
        { token: (i) => `event item ${i} date`, share: 0.2 },
        { token: (i) => `event item ${i} time`, share: 0.14 },
        { token: (i) => `event item ${i} venue`, share: 0.28 },
      ],
      { heading: word("event title") },
    ),
};

/** The blocks each post type offers. The line up and an other post have their own buttons. */
export const TYPE_BLOCKS: Partial<Record<PostType, TypeBlock[]>> = {
  fixtures: [fixturesList],
  results: [resultsList],
  result: [finalScore, performers, potm],
  motm: [potm, stats],
  totw: [team],
  milestones: [milestoneList],
  announcement: [announce],
  toss: [toss],
  events: [eventDetails, eventList],
};

const range = (n: number) => Array.from({ length: n }, (_, i) => i + 1);

/** Every single field a post type can hold, in the order the picker lists them. */
export function typeFieldTokens(type: PostType): string[] {
  const rows = (word: string, max: number, fields: string[]) =>
    range(max).flatMap((n) => fields.map((f) => `${word} ${n} ${f}`));
  switch (type) {
    case "fixtures":
      return rows("fixture", 8, [
        "opponent",
        "grade",
        "time",
        "venue",
        "home away",
        "short",
      ]);
    case "results":
      return rows("result", 8, [
        "opponent",
        "grade",
        "our score",
        "their score",
        "outcome",
        "margin",
      ]);
    case "result":
      return [
        "our score",
        "opponent score",
        "our overs",
        "opponent overs",
        "result",
        "margin",
        "winner",
        "grade",
        "potm name",
        "potm role",
        "potm bat",
        "potm bowl",
        "potm line",
        "potm photo",
        ...["our", "opponent"].flatMap((side) =>
          ["batter", "bowler"].flatMap((kind) =>
            range(3).flatMap((n) => [
              `${side} ${kind} ${n} name`,
              `${side} ${kind} ${n} line`,
            ]),
          ),
        ),
      ];
    case "motm":
      return [
        "potm name",
        "potm first",
        "potm last",
        "potm role",
        "potm line",
        "potm summary",
        "potm photo",
        ...rows("stat", 6, ["label", "value"]),
      ];
    case "totw":
      return [
        "totw heading",
        ...rows("totw", 15, [
          "name",
          "first",
          "last",
          "line",
          "grade",
          "opponent",
          "points",
          "photo",
        ]),
      ];
    case "milestones":
      return [
        "milestone title",
        ...rows("milestone", 8, [
          "name",
          "first",
          "last",
          "value",
          "unit",
          "date",
          "photo",
        ]),
      ];
    case "announcement":
      return [
        "announcement headline",
        "announcement subheadline",
        "announcement kind",
        "announcement name",
        "announcement first",
        "announcement last",
        "announcement photo",
      ];
    case "toss":
      return ["toss", "toss winner", "toss decision"];
    case "events":
      return [
        "event kicker",
        "event title",
        "event subtitle",
        "event date",
        "event time",
        "event venue",
        "event price",
        "event cta",
        "event sponsor",
        "event photo",
        ...rows("event item", 8, ["title", "date", "time", "venue", "price"]),
      ];
    default:
      return [];
  }
}
