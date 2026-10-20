import {
  FIELD_TOKENS,
  featuredPhotoBlock,
  fieldBlock,
  lineUpBlock,
  matchDetailsBlock,
  MAX_LINEUP,
  playerExtraBlock,
  PLAYER_EXTRAS,
  sponsorsBlock,
} from "../blocks";
import { bindFromToken } from "../tokens";
import type { PageSize } from "../blocks";
import { extractFields, isError } from "../extract";
import { group, must, page, textBox } from "./fakePage";

const SIZES: PageSize[] = [
  { width: 1080, height: 1080 },
  { width: 1080, height: 1350 },
  { width: 1080, height: 1920 },
  { width: 800, height: 600 },
  { width: 2160, height: 2160 },
];

describe("lineUpBlock", () => {
  it("makes a heading and one {{player N}} box per place", () => {
    const b = lineUpBlock({ width: 1080, height: 1080 }, 11);
    expect(b.boxes.map((x) => x.text)).toEqual([
      "LINE UP",
      ...Array.from({ length: 11 }, (_, i) => `{{player ${i + 1}}}`),
    ]);
  });

  it("can leave out the heading", () => {
    const b = lineUpBlock({ width: 1080, height: 1080 }, 3, false);
    expect(b.boxes.map((x) => x.text)).toEqual([
      "{{player 1}}",
      "{{player 2}}",
      "{{player 3}}",
    ]);
  });

  it("keeps the count between 1 and the lineup ceiling", () => {
    const n = (c: number) =>
      lineUpBlock({ width: 1080, height: 1080 }, c, false).boxes.length;
    expect([n(0), n(-4), n(NaN), n(99), n(2.6)]).toEqual([
      1,
      1,
      1,
      MAX_LINEUP,
      3,
    ]);
  });

  it.each(SIZES)("fits every count on a $width x $height page", (size) => {
    for (let n = 1; n <= MAX_LINEUP; n++) {
      const { boxes } = lineUpBlock(size, n);
      for (const box of boxes) {
        expect(box.left).toBeGreaterThanOrEqual(0);
        expect(box.left + box.width).toBeLessThanOrEqual(size.width);
        expect(box.top).toBeGreaterThanOrEqual(0);
        // The box's text line must end inside the page.
        expect(box.top + box.fontSize * 1.4).toBeLessThanOrEqual(size.height);
        expect(box.fontSize).toBeGreaterThanOrEqual(10);
        // Rows are capped at 6% of the page height; the heading is 1.2 times a row.
        const cap = box.text === "LINE UP" ? 1.2 : 1;
        expect(box.fontSize).toBeLessThanOrEqual(size.height * 0.06 * cap + 1);
      }
      // No two rows overlap: each starts below the previous one's text.
      for (let i = 1; i < boxes.length; i++) {
        const prev = must(boxes[i - 1]);
        expect(must(boxes[i]).top).toBeGreaterThanOrEqual(
          prev.top + Math.floor(prev.fontSize * 1.2),
        );
      }
    }
  });

  it("makes the type smaller as places are added", () => {
    const size = { width: 1080, height: 1080 };
    const fs = (n: number) =>
      must(lineUpBlock(size, n, false).boxes[0]).fontSize;
    expect(fs(5)).toBeGreaterThan(fs(11));
    expect(fs(11)).toBeGreaterThan(fs(15));
  });

  it("makes the heading bold and bigger than the rows", () => {
    const [h, row] = lineUpBlock({ width: 1080, height: 1080 }, 11).boxes;
    expect(must(h).bold).toBe(true);
    expect(must(row).bold).toBe(false);
    expect(must(h).fontSize).toBeGreaterThan(must(row).fontSize);
  });

  it("round-trips: what is laid out is what the reader finds", () => {
    const size = { width: 1080, height: 1350 };
    const block = lineUpBlock(size, 11);
    const inGroup = group(
      block.boxes.map((b) =>
        textBox(b.text, {
          top: b.top - 40,
          left: b.left - 30,
          width: b.width,
          format: { fontSize: b.fontSize, color: b.color, textAlign: b.align },
        }),
      ),
      { top: 40, left: 30 },
    );
    const r = extractFields(page([inGroup], size));
    if (isError(r)) {
      throw new Error(r.error);
    }
    expect(r.fields.map((f) => f.token)).toEqual(
      Array.from({ length: 11 }, (_, i) => `player ${i + 1}`),
    );
    expect(r.fields.every((f) => f.binding?.startsWith("lineup."))).toBe(true);
    // The heading is plain text, so it is not a field and not reported.
    expect(r.skipped).toEqual([]);
    const players = block.boxes.slice(1);
    expect(r.fields.map((f) => [f.x, f.y])).toEqual(
      players.map((b) => [b.left, b.top]),
    );
  });
});

describe("matchDetailsBlock", () => {
  it("holds the match details a post usually carries", () => {
    const b = matchDetailsBlock({ width: 1080, height: 1080 });
    expect(b.boxes.map((x) => x.text)).toEqual([
      "{{opponent}}",
      "{{date}}",
      "{{time}}",
      "{{venue}}",
      "{{competition}}",
      "{{round}}",
    ]);
  });

  it.each(SIZES)("fits a $width x $height page", (size) => {
    for (const box of matchDetailsBlock(size).boxes) {
      expect(box.left + box.width).toBeLessThanOrEqual(size.width);
      expect(box.top + box.fontSize * 1.4).toBeLessThanOrEqual(size.height);
    }
  });

  it("sits to the right of the line up, not on top of it", () => {
    const size = { width: 1080, height: 1080 };
    const lineUpRight = Math.max(
      ...lineUpBlock(size, 11).boxes.map((b) => b.left + b.width),
    );
    const detailsLeft = Math.min(
      ...matchDetailsBlock(size).boxes.map((b) => b.left),
    );
    expect(detailsLeft).toBeGreaterThan(lineUpRight);
  });
});

describe("fieldBlock", () => {
  const size = { width: 1080, height: 1080 };

  it("is one box holding one token, named plainly", () => {
    const b = fieldBlock(size, "player 3");
    expect(b.name).toBe("Player 3");
    expect(b.boxes.map((x) => x.text)).toEqual(["{{player 3}}"]);
  });

  it("offers only tokens BetterCricket understands, with no repeats", () => {
    expect(FIELD_TOKENS.every((t) => bindFromToken(t) != null)).toBe(true);
    expect(new Set(FIELD_TOKENS).size).toBe(FIELD_TOKENS.length);
    expect(FIELD_TOKENS).toContain("player 15");
    expect(FIELD_TOKENS).toContain("opponent");
  });

  it("steps each new box down, so a run of them does not stack", () => {
    const tops = [0, 1, 2, 3].map(
      (i) => must(fieldBlock(size, "date", i).boxes[0]).top,
    );
    expect(new Set(tops).size).toBe(4);
    expect(tops).toEqual([...tops].sort((a, b) => a - b));
  });

  it.each([
    { width: 1080, height: 1080 },
    { width: 1080, height: 1350 },
    { width: 1080, height: 1920 },
    { width: 800, height: 600 },
  ])("stays inside a $width x $height page for every slot", (page) => {
    for (let slot = 0; slot < 20; slot++) {
      const box = must(fieldBlock(page, "venue", slot).boxes[0]);
      expect(box.left + box.width).toBeLessThanOrEqual(page.width);
      expect(box.top + box.fontSize * 1.4).toBeLessThanOrEqual(page.height);
    }
  });
});

describe("area and mark blocks", () => {
  it("a sponsors box is a rectangle with {{sponsors}} inside it", () => {
    for (const size of SIZES) {
      const b = sponsorsBlock(size);
      const r = must(b.rects?.[0]);
      const t = must(b.boxes[0]);
      expect(t.text).toBe("{{sponsors}}");
      expect(t.left).toBe(r.left);
      expect(t.width).toBe(r.width);
      expect(t.top).toBeGreaterThanOrEqual(r.top);
      expect(t.top).toBeLessThan(r.top + r.height);
      expect(r.left + r.width).toBeLessThanOrEqual(size.width);
      expect(r.top + r.height).toBeLessThanOrEqual(size.height);
    }
  });

  it("a photo area is a square with the player's photo word in it", () => {
    const b = playerExtraBlock({ width: 1080, height: 1080 }, 4, "photo");
    const r = must(b.rects?.[0]);
    expect(r.width).toBe(r.height);
    expect(must(b.boxes[0]).text).toBe("{{player 4 photo}}");
    expect(b.name).toBe("Player 4 (photo)");
  });

  it("every extra becomes a token BetterCricket knows", () => {
    for (const e of PLAYER_EXTRAS) {
      const b = playerExtraBlock({ width: 1080, height: 1080 }, 2, e);
      const text = must(b.boxes[0]).text;
      expect(bindFromToken(text)).toMatch(/^lineup\.2\./);
    }
  });

  it("a mark is a plain box with no rectangle", () => {
    const b = playerExtraBlock({ width: 1080, height: 1080 }, 1, "captain");
    expect(b.rects).toBeUndefined();
    expect(must(b.boxes[0]).text).toBe("{{player 1 captain}}");
  });
});

describe("featuredPhotoBlock", () => {
  it("is a photo area with the featured photo word in it, inside the page", () => {
    for (const size of SIZES) {
      const b = featuredPhotoBlock(size);
      const r = must(b.rects?.[0]);
      expect(must(b.boxes[0]).text).toBe("{{photo}}");
      expect(bindFromToken("{{photo}}")).toBe("photo");
      expect(r.left + r.width).toBeLessThanOrEqual(size.width);
      expect(r.top + r.height).toBeLessThanOrEqual(size.height);
    }
  });
});
