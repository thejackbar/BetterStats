import { visualBounds } from "../describe";
import { extractFields, isError } from "../extract";
import type { Extraction } from "../types";
import { group, page, rect, shape, textBox } from "./fakePage";

const ok = (r: ReturnType<typeof extractFields>): Extraction => {
  if (isError(r)) {
    throw new Error(r.error);
  }
  return r;
};

const SIZE = { width: 1080, height: 1080 };
const onPage = (els: Parameters<typeof page>[0], dims = SIZE) =>
  ok(extractFields(page(els, dims)));

describe("visualBounds", () => {
  it("is the element's own box when upright", () => {
    expect(visualBounds(10, 20, 300, 100, 0)).toEqual({
      x: 10,
      y: 20,
      w: 300,
      h: 100,
    });
  });

  it("swaps width and height about the centre for a quarter turn", () => {
    const v = visualBounds(-376, 582, 1346, 451, 90);
    expect(v.w).toBeCloseTo(451, 5);
    expect(v.h).toBeCloseTo(1346, 5);
    expect(v.x).toBeCloseTo(-376 + 1346 / 2 - 451 / 2, 5);
    expect(v.y).toBeCloseTo(582 + 451 / 2 - 1346 / 2, 5);
  });

  it("is the same for a half turn, and for a negative quarter turn", () => {
    const a = visualBounds(0, 0, 200, 100, 180);
    expect(a.w).toBeCloseTo(200, 5);
    expect(a.h).toBeCloseTo(100, 5);
    const b = visualBounds(0, 0, 200, 100, -90);
    expect(b.w).toBeCloseTo(100, 5);
    expect(b.h).toBeCloseTo(200, 5);
  });

  it("grows to fit a tilt", () => {
    const v = visualBounds(0, 0, 100, 100, 45);
    expect(v.w).toBeCloseTo(141.42, 1);
    expect(v.h).toBeCloseTo(141.42, 1);
  });
});

describe("panels", () => {
  it("finds the maroon torn-paper panel: a rotated picture behind the lineup", () => {
    const r = onPage([
      // the grunge background: a picture bigger than the page
      rect({ left: 0, top: -275, width: 1200, height: 1690, media: "image" }),
      // the panel: a wide picture turned a quarter turn
      rect({
        left: -376,
        top: 582,
        width: 1346,
        height: 451,
        rotation: 90,
        media: "image",
      }),
      textBox("LINE UP", { top: 214, left: 164, width: 753, height: 60 }),
      textBox("{{player 1}}", { top: 317, left: 164, width: 753, height: 50 }),
      textBox("{{player 11}}", { top: 893, left: 164, width: 753, height: 50 }),
      textBox("{{opponent}}", { top: 135, left: 564, width: 899, height: 60 }),
    ]);
    expect(r.surfaces.map((s) => s.use)).toEqual(["background", "panel"]);
    expect(r.panels).toHaveLength(1);
    const [p] = r.panels;
    expect(p?.source).toBe("picture");
    expect(p?.color).toBeNull();
    // 451 wide, from the left of the page's turned footprint, cut off at the bottom of the page
    expect(Math.abs((p?.w ?? 0) - 451)).toBeLessThanOrEqual(1);
    // Within a pixel: the turned footprint starts at x 71.5 and y 134.5.
    expect(Math.abs((p?.x ?? 0) - 71.5)).toBeLessThanOrEqual(1);
    expect(Math.abs((p?.y ?? 0) - 134.5)).toBeLessThanOrEqual(1);
    expect((p?.y ?? 0) + (p?.h ?? 0)).toBe(1080);
  });

  it("uses a solid colour when the surface has one", () => {
    const r = onPage([
      rect({ left: 50, top: 50, width: 400, height: 600, colour: "#7B3B3B" }),
      textBox("{{player 1}}", { top: 100, left: 80, width: 300, height: 40 }),
    ]);
    expect(r.panels).toEqual([
      {
        x: 50,
        y: 50,
        w: 400,
        h: 600,
        color: "#7b3b3b",
        source: "solid",
        imageRef: null,
        box: null,
      },
    ]);
  });

  describe("pictures", () => {
    const words = textBox("{{player 1}}", {
      top: 400,
      left: 60,
      width: 300,
      height: 40,
    });

    it("keeps the id and the unturned box of a picture panel", () => {
      const r = onPage([
        rect({
          left: 50,
          top: 100,
          width: 400,
          height: 800,
          rotation: 90,
          media: "image",
          imageRef: "paper",
        }),
        words,
      ]);
      expect(r.panels).toHaveLength(1);
      expect(r.panels[0]).toMatchObject({
        source: "picture",
        imageRef: "paper",
        box: { x: 50, y: 100, w: 400, h: 800, rotation: 90 },
      });
    });

    it("scales the box with the page", () => {
      const r = onPage(
        [
          rect({
            left: 25,
            top: 50,
            width: 200,
            height: 400,
            media: "image",
            imageRef: "paper",
          }),
          textBox("{{player 1}}", {
            top: 100,
            left: 40,
            width: 100,
            height: 20,
          }),
        ],
        { width: 540, height: 540 },
      );
      expect(r.panels[0]?.box).toEqual({
        x: 50,
        y: 100,
        w: 400,
        h: 800,
        rotation: 0,
      });
    });

    it("has no box for a picture Canva gave no id for", () => {
      const r = onPage([
        rect({
          left: 50,
          top: 100,
          width: 400,
          height: 800,
          media: "image",
        }),
        words,
      ]);
      expect(r.panels[0]).toMatchObject({ imageRef: null, box: null });
    });

    it("takes a picture covering the page as the background", () => {
      const r = onPage([
        rect({ width: 1080, height: 1080, media: "image", imageRef: "bg" }),
        words,
      ]);
      expect(r.backgroundRef).toBe("bg");
      expect(r.panels).toEqual([]);
    });

    it("has no background picture for a solid page", () => {
      const r = onPage([
        rect({ width: 1080, height: 1080, colour: "#112233" }),
        words,
      ]);
      expect(r.backgroundRef).toBeNull();
    });
  });

  it("calls a vector shape with mixed fills a shape panel", () => {
    const r = onPage([
      shape({
        left: 50,
        top: 50,
        width: 400,
        height: 600,
        paths: [
          { d: "M0 0", colour: "#111111" },
          { d: "M1 1", colour: "#222222" },
        ],
      }),
      textBox("{{player 1}}", { top: 100, left: 80, width: 300, height: 40 }),
    ]);
    expect(r.panels).toMatchObject([{ source: "shape", color: null }]);
  });

  it("marks a surface covering the page as the background, and makes no panel of it", () => {
    const r = onPage([
      rect({ width: 1080, height: 1080, colour: "#ffffff" }),
      textBox("{{player 1}}", { top: 100, left: 80, width: 300, height: 40 }),
    ]);
    expect(r.panels).toEqual([]);
    expect(r.surfaces.map((s) => s.use)).toEqual(["background"]);
  });

  it("treats a turned picture that covers the page as the background", () => {
    const r = onPage([
      rect({
        left: -310,
        top: 310,
        width: 1700,
        height: 1080,
        rotation: 90,
        media: "image",
      }),
      textBox("{{player 1}}", { top: 100, left: 80, width: 300, height: 40 }),
    ]);
    expect(r.surfaces.map((s) => s.use)).toEqual(["background"]);
  });

  it("leaves out a picture with no text on it", () => {
    const r = onPage([
      rect({ left: 600, top: 600, width: 300, height: 300, media: "image" }),
      textBox("{{player 1}}", { top: 100, left: 80, width: 300, height: 40 }),
    ]);
    expect(r.panels).toEqual([]);
    expect(r.surfaces.map((s) => s.use)).toEqual(["left_out"]);
  });

  it("leaves out a surface that is too small, off the page, a video or empty", () => {
    const text = textBox("{{player 1}}", {
      top: 10,
      left: 10,
      width: 80,
      height: 30,
    });
    const r = onPage([
      rect({ left: 0, top: 0, width: 40, height: 40, colour: "#111111" }),
      rect({
        left: 2000,
        top: 2000,
        width: 300,
        height: 300,
        colour: "#111111",
      }),
      rect({ left: 0, top: 0, width: 300, height: 300, media: "video" }),
      rect({ left: 0, top: 0, width: 300, height: 300 }),
      text,
    ]);
    expect(r.panels).toEqual([]);
    expect(r.surfaces.every((s) => s.use === "left_out")).toBe(true);
  });

  it("leaves out a surface in a rotated group", () => {
    const r = onPage([
      group([rect({ width: 400, height: 400, colour: "#111111" })], {
        rotation: 30,
      }),
      textBox("{{player 1}}", { top: 100, left: 80, width: 300, height: 40 }),
    ]);
    expect(r.panels).toEqual([]);
  });

  it("finds a panel inside an upright group, in place", () => {
    const r = onPage([
      group(
        [rect({ top: 5, left: 5, width: 300, height: 400, colour: "#111111" })],
        {
          top: 100,
          left: 200,
        },
      ),
      textBox("{{player 1}}", { top: 150, left: 250, width: 200, height: 40 }),
    ]);
    expect(r.panels[0]).toMatchObject({ x: 205, y: 105, w: 300, h: 400 });
  });

  it("keeps the larger of two surfaces covering the same place", () => {
    const r = onPage([
      rect({ left: 50, top: 50, width: 400, height: 600, colour: "#111111" }),
      rect({ left: 60, top: 60, width: 380, height: 580, media: "image" }),
      textBox("{{player 1}}", { top: 100, left: 80, width: 300, height: 40 }),
    ]);
    expect(r.panels).toHaveLength(1);
    expect(r.panels[0]).toMatchObject({ w: 400, h: 600 });
    expect(r.surfaces.map((s) => s.use)).toEqual(["panel", "left_out"]);
  });

  it("keeps two panels that do not overlap", () => {
    const r = onPage([
      rect({ left: 20, top: 20, width: 300, height: 300, colour: "#111111" }),
      rect({ left: 600, top: 600, width: 300, height: 300, colour: "#222222" }),
      textBox("{{player 1}}", { top: 100, left: 80, width: 100, height: 40 }),
      textBox("{{date}}", { top: 700, left: 650, width: 100, height: 40 }),
    ]);
    expect(r.panels).toHaveLength(2);
  });

  it("keeps at most six panels", () => {
    const els = Array.from({ length: 8 }, (_, i) => [
      rect({
        left: 10 + i * 120,
        top: 10,
        width: 100,
        height: 100,
        colour: "#111111",
      }),
      textBox("hi", { top: 20, left: 20 + i * 120, width: 60, height: 20 }),
    ]).flat();
    expect(onPage(els).panels).toHaveLength(6);
  });

  it("scales a panel with the page", () => {
    const r = ok(
      extractFields(
        page(
          [
            rect({
              left: 100,
              top: 200,
              width: 800,
              height: 1200,
              colour: "#111111",
            }),
            textBox("{{player 1}}", {
              top: 300,
              left: 200,
              width: 400,
              height: 80,
            }),
          ],
          { width: 2160, height: 2160 },
        ),
      ),
    );
    expect(r.panels[0]).toMatchObject({ x: 50, y: 100, w: 400, h: 600 });
  });

  it("counts fixed words and skipped boxes as text on the panel", () => {
    const r = onPage([
      rect({ left: 50, top: 50, width: 400, height: 600, colour: "#111111" }),
      textBox("LINE UP", { top: 100, left: 80, width: 300, height: 40 }),
    ]);
    expect(r.panels).toHaveLength(1);
  });

  it("makes no panel when there is nothing behind the text", () => {
    expect(onPage([textBox("{{player 1}}")]).panels).toEqual([]);
  });

  it("goes by where the words start: a wide left-aligned box that runs past the panel is still on it", () => {
    const r = onPage([
      rect({ left: 70, top: 100, width: 450, height: 900, colour: "#111111" }),
      // 753 wide, so its middle is off the panel, but the words start on it
      textBox("{{player 1}}", { top: 300, left: 164, width: 753, height: 50 }),
    ]);
    expect(r.panels).toHaveLength(1);
  });

  it("a wide left-aligned box that STARTS beyond the panel is not on it", () => {
    const r = onPage([
      rect({ left: 70, top: 100, width: 300, height: 900, colour: "#111111" }),
      textBox("{{player 1}}", { top: 300, left: 400, width: 600, height: 50 }),
    ]);
    expect(r.panels).toEqual([]);
  });

  it("goes by the middle for centred text and the right edge for right-aligned text", () => {
    const panel = rect({
      left: 600,
      top: 100,
      width: 300,
      height: 600,
      colour: "#111111",
    });
    const centred = onPage([
      panel,
      textBox("{{date}}", {
        top: 200,
        left: 400,
        width: 400,
        height: 40,
        format: { textAlign: "center" },
      }),
    ]);
    expect(centred.panels).toHaveLength(1);
    const right = onPage([
      panel,
      textBox("{{date}}", {
        top: 200,
        left: 300,
        width: 580,
        height: 40,
        format: { textAlign: "end" },
      }),
    ]);
    expect(right.panels).toHaveLength(1);
    const wrongSide = onPage([
      panel,
      textBox("{{date}}", {
        top: 200,
        left: 300,
        width: 580,
        height: 40,
        format: { textAlign: "start" },
      }),
    ]);
    expect(wrongSide.panels).toEqual([]);
  });
});
