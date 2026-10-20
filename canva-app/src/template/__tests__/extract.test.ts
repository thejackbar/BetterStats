import { buildTemplateFile } from "../buildFile";
import { extractFields, fitToPost, isError, nameFonts } from "../extract";
import type { Extraction } from "../types";
import { group, page, rect, shape, textBox } from "./fakePage";

const ok = (r: ReturnType<typeof extractFields>): Extraction => {
  if (isError(r)) {
    throw new Error(r.error);
  }
  return r;
};

describe("fitToPost", () => {
  it.each([
    [1080, 1080, 1080, 1080, true, 1],
    [1080, 1350, 1080, 1350, true, 1],
    [1080, 1920, 1080, 1920, true, 1],
    [2160, 2700, 1080, 1350, true, 0.5],
    [540, 540, 1080, 1080, true, 2],
    [1920, 1080, 1080, 608, false, 1080 / 1920],
    [1080, 1100, 1080, 1100, false, 1],
  ])("%d x %d", (w, h, cw, ch, post, scale) => {
    const r = fitToPost(w, h);
    expect(r.canvas).toEqual({ w: cw, h: ch });
    expect(r.postSize).toBe(post);
    expect(r.scale).toBeCloseTo(scale as number, 5);
  });
});

describe("extractFields", () => {
  it("reads a text box that holds one token, with its look", () => {
    const r = ok(
      extractFields(
        page([
          textBox("{{player 1}}", {
            top: 300,
            left: 90,
            width: 600,
            format: {
              fontSize: 44,
              textAlign: "center",
              color: "#ffe14d",
              fontWeight: "bold",
              fontRef: "font-anton",
            },
          }),
        ]),
      ),
    );
    expect(r.fields).toEqual([
      {
        token: "player 1",
        binding: "lineup.1.name",
        x: 90,
        y: 300,
        w: 600,
        fontRef: "font-anton",
        fontFamily: null,
        fontSize: 44,
        h: null,
        bold: true,
        color: "#ffe14d",
        colorRole: "accent",
        fontRole: "display",
        align: "center",
        uppercase: false,
      },
    ]);
    expect(r.skipped).toEqual([]);
    expect(r.warnings).toEqual([]);
  });

  it("ignores text with no token, and shapes", () => {
    const r = ok(extractFields(page([textBox("LINEUP"), rect(), shape()])));
    expect(r.fields).toEqual([]);
    expect(r.skipped).toEqual([]);
  });

  it("fills in what Canva leaves out", () => {
    const f = ok(extractFields(page([textBox("{{opponent}}")]))).fields[0];
    expect(f).toMatchObject({
      fontSize: 16,
      bold: false,
      color: null,
      align: "left",
      fontRef: null,
    });
  });

  it("maps alignment and weights", () => {
    const align = (a: "start" | "center" | "end" | "justify") =>
      ok(
        extractFields(
          page([textBox("{{date}}", { format: { textAlign: a } })]),
        ),
      ).fields[0]?.align;
    expect([
      align("start"),
      align("center"),
      align("end"),
      align("justify"),
    ]).toEqual(["left", "center", "right", "left"]);
    const bold = (w: string) =>
      ok(
        extractFields(
          page([textBox("{{date}}", { format: { fontWeight: w } })]),
        ),
      ).fields[0]?.bold;
    expect(["normal", "light", "medium"].map(bold)).toEqual([
      false,
      false,
      false,
    ]);
    expect(["semibold", "bold", "ultrabold", "heavy"].map(bold)).toEqual([
      true,
      true,
      true,
      true,
    ]);
  });

  it("asks for capitals only when the token is in capitals", () => {
    const r = ok(
      extractFields(page([textBox("{{PLAYER 1}}"), textBox("{{player 2}}")])),
    );
    expect(r.fields.map((f) => f.uppercase)).toEqual([true, false]);
  });

  it("keeps a word that is not a field, and marks it unknown", () => {
    const r = ok(extractFields(page([textBox("{{batsman 1}}")])));
    expect(r.fields[0]).toMatchObject({ token: "batsman 1", binding: null });
  });

  it("keeps two boxes with the same token", () => {
    const r = ok(
      extractFields(page([textBox("{{opponent}}"), textBox("{{opponent}}")])),
    );
    expect(r.fields).toHaveLength(2);
  });

  it("leaves out and reports a token among other words", () => {
    const r = ok(extractFields(page([textBox("vs {{opponent}} today")])));
    expect(r.fields).toEqual([]);
    expect(r.skipped).toEqual([
      { reason: "mixed", text: "vs {{opponent}} today" },
    ]);
  });

  it("reads a locked box, since nothing on the page is changed", () => {
    const r = ok(extractFields(page([textBox("{{date}}", { locked: true })])));
    expect(r.fields.map((f) => f.token)).toEqual(["date"]);
    expect(r.skipped).toEqual([]);
  });

  it("reads a box inside a group, with the group's position added back in", () => {
    const r = ok(
      extractFields(
        page([
          group([textBox("{{player 1}}", { top: 20, left: 10, width: 300 })], {
            top: 200,
            left: 100,
          }),
        ]),
      ),
    );
    expect(r.fields[0]).toMatchObject({ x: 110, y: 220, w: 300 });
    expect(r.skipped).toEqual([]);
  });

  it("adds up nested groups", () => {
    const r = ok(
      extractFields(
        page([
          group(
            [
              group([textBox("{{player 1}}", { top: 5, left: 7 })], {
                top: 50,
                left: 30,
              }),
            ],
            { top: 200, left: 100 },
          ),
        ]),
      ),
    );
    expect(r.fields[0]).toMatchObject({ x: 137, y: 255 });
  });

  it("scales a grouped box with the page", () => {
    const r = ok(
      extractFields(
        page(
          [
            group([textBox("{{date}}", { top: 100, left: 20 })], {
              top: 400,
              left: 160,
            }),
          ],
          { width: 2160, height: 2160 },
        ),
      ),
    );
    expect(r.fields[0]).toMatchObject({ x: 90, y: 250 });
  });

  it("leaves out and reports a box in a rotated group", () => {
    const r = ok(
      extractFields(page([group([textBox("{{player 1}}")], { rotation: 30 })])),
    );
    expect(r.fields).toEqual([]);
    expect(r.skipped).toEqual([
      { reason: "rotated_group", text: "{{player 1}}" },
    ]);
  });

  it("reads a box in a locked group", () => {
    const r = ok(
      extractFields(page([group([textBox("{{player 1}}")], { locked: true })])),
    );
    expect(r.fields.map((f) => f.token)).toEqual(["player 1"]);
    expect(r.skipped).toEqual([]);
  });

  it("still reads a plain box beside a group", () => {
    const r = ok(
      extractFields(
        page([
          textBox("{{date}}", { top: 1, left: 2 }),
          group([textBox("{{player 1}}", { top: 3, left: 4 })], {
            top: 10,
            left: 10,
          }),
        ]),
      ),
    );
    expect(r.fields.map((f) => [f.token, f.x, f.y])).toEqual([
      ["date", 2, 1],
      ["player 1", 14, 13],
    ]);
  });

  it("warns about a rotated box but still reads it", () => {
    const r = ok(extractFields(page([textBox("{{date}}", { rotation: 15 })])));
    expect(r.fields).toHaveLength(1);
    expect(r.warnings.join(" ")).toMatch(/{{date}} is rotated/);
  });

  it("scales positions, widths and type to a 1080 wide post", () => {
    const r = ok(
      extractFields(
        page(
          [
            textBox("{{player 1}}", {
              top: 600,
              left: 180,
              width: 1200,
              format: { fontSize: 88 },
            }),
          ],
          { width: 2160, height: 2700 },
        ),
      ),
    );
    expect(r.canvas).toEqual({ w: 1080, h: 1350 });
    expect(r.fields[0]).toMatchObject({ x: 90, y: 300, w: 600, fontSize: 44 });
    expect(r.postSize).toBe(true);
  });

  it("warns when the page is not a post shape", () => {
    const r = ok(
      extractFields(page([textBox("{{date}}")], { width: 1920, height: 1080 })),
    );
    expect(r.postSize).toBe(false);
    expect(r.warnings.join(" ")).toMatch(/1920 x 1080/);
  });

  it("explains a page with no size", () => {
    // `page()` fills in a size when given undefined, so remove it afterwards.
    const r = extractFields({ ...page([]), dimensions: undefined });
    expect(isError(r)).toBe(true);
    expect(isError(r) ? r.error : "").toMatch(/whiteboard/);
  });
});

describe("fixed words and roles", () => {
  it("carries plain text as fixed words, with its look and place", () => {
    const r = ok(
      extractFields(
        page([
          textBox("LINE UP", {
            top: 240,
            left: 165,
            width: 400,
            format: { fontSize: 40, fontWeight: "bold", color: "#ffffff" },
          }),
          textBox("{{player 1}}"),
        ]),
      ),
    );
    expect(r.texts).toEqual([
      {
        text: "LINE UP",
        x: 165,
        y: 240,
        w: 400,
        fontRef: null,
        fontFamily: null,
        fontSize: 40,
        bold: true,
        color: "#ffffff",
        colorRole: "ink",
        fontRole: "display",
        align: "left",
        uppercase: true,
      },
    ]);
    expect(r.fields).toHaveLength(1);
  });

  it("does not carry empty text, or a token among other words as fixed text", () => {
    const r = ok(
      extractFields(page([textBox("   "), textBox("vs {{opponent}}")])),
    );
    expect(r.texts).toEqual([]);
    expect(r.skipped.map((x) => x.reason)).toEqual(["mixed"]);
  });

  it("carries fixed words from inside a group, in place", () => {
    const r = ok(
      extractFields(
        page([
          group([textBox("SATURDAY", { top: 5, left: 7 })], {
            top: 100,
            left: 200,
          }),
        ]),
      ),
    );
    expect(r.texts[0]).toMatchObject({ text: "SATURDAY", x: 207, y: 105 });
  });

  it("leaves out fixed words in a rotated group", () => {
    const r = ok(
      extractFields(page([group([textBox("SATURDAY")], { rotation: 30 })])),
    );
    expect(r.texts).toEqual([]);
  });

  it("scales fixed words with the page", () => {
    const r = ok(
      extractFields(
        page(
          [
            textBox("HELLO", {
              top: 400,
              left: 160,
              width: 800,
              format: { fontSize: 100 },
            }),
          ],
          { width: 2160, height: 2160 },
        ),
      ),
    );
    expect(r.texts[0]).toMatchObject({ x: 80, y: 200, w: 400, fontSize: 50 });
  });

  it("keeps at most 40 fixed words", () => {
    const many = Array.from({ length: 60 }, (_, i) => textBox(`word ${i}`));
    expect(ok(extractFields(page(many))).texts).toHaveLength(40);
  });
});

describe("nameFonts", () => {
  const base = (): Extraction =>
    ok(
      extractFields(
        page([
          textBox("{{player 1}}", { format: { fontRef: "a" } }),
          textBox("{{player 2}}", { format: { fontRef: "a" } }),
          textBox("{{date}}", { format: { fontRef: "b" } }),
          textBox("{{venue}}"),
        ]),
      ),
    );

  it("names each font once and fills every box that uses it", async () => {
    const lookup = jest.fn(async () => [
      { ref: "a", name: "Anton" },
      { ref: "b", name: "Inter" },
    ]);
    const r = await nameFonts(base(), lookup);
    expect(lookup).toHaveBeenCalledTimes(1);
    expect(lookup).toHaveBeenCalledWith(["a", "b"]);
    expect(r.fields.map((f) => f.fontFamily)).toEqual([
      "Anton",
      "Anton",
      "Inter",
      null,
    ]);
    expect(r.warnings).toEqual([]);
  });

  it("leaves a font Canva would not name empty, without a fuss", async () => {
    const r = await nameFonts(base(), async () => [
      { ref: "a", name: "Anton" },
    ]);
    expect(r.fields[2]?.fontFamily).toBeNull();
    expect(r.warnings).toEqual([]);
  });

  it("carries on when the lookup fails", async () => {
    const r = await nameFonts(base(), async () => {
      throw new Error("offline");
    });
    expect(r.fields.every((f) => f.fontFamily == null)).toBe(true);
    expect(r.warnings).toEqual([]);
  });

  it("names the fonts on fixed words too, in the same lookup", async () => {
    const e = ok(
      extractFields(
        page([
          textBox("{{player 1}}", { format: { fontRef: "a" } }),
          textBox("LINE UP", { format: { fontRef: "b" } }),
        ]),
      ),
    );
    const lookup = jest.fn(async () => [
      { ref: "a", name: "Anton" },
      { ref: "b", name: "Oswald" },
    ]);
    const r = await nameFonts(e, lookup);
    expect(lookup).toHaveBeenCalledTimes(1);
    expect(lookup).toHaveBeenCalledWith(["a", "b"]);
    expect(r.texts[0]?.fontFamily).toBe("Oswald");
  });

  it("does not look anything up when no box has a font", async () => {
    const lookup = jest.fn(async () => []);
    await nameFonts(ok(extractFields(page([textBox("{{date}}")]))), lookup);
    expect(lookup).not.toHaveBeenCalled();
  });
});

describe("buildTemplateFile", () => {
  it("writes the file BetterCricket reads", async () => {
    const e = await nameFonts(
      ok(
        extractFields(
          page([
            textBox("{{PLAYER 1}}", {
              top: 300,
              left: 90,
              width: 600,
              format: { fontSize: 44, color: "#ffe14d", fontRef: "a" },
            }),
          ]),
        ),
      ),
      async () => [{ ref: "a", name: "Anton" }],
    );
    expect(
      buildTemplateFile(e, {
        name: "  LineUp  ",
        postType: "lineup",
        pictures: {
          background: "data:image/png;base64,AAAA",
          byRef: new Map(),
        },
      }),
    ).toEqual({
      format: "bettercricket-template",
      version: 1,
      name: "LineUp",
      postType: "lineup",
      canvas: { w: 1080, h: 1080 },
      background: "data:image/png;base64,AAAA",
      fields: [
        {
          token: "PLAYER 1",
          x: 90,
          y: 300,
          w: 600,
          fontFamily: "Anton",
          fontSize: 44,
          bold: false,
          color: "#ffe14d",
          colorRole: "accent",
          fontRole: "body",
          align: "left",
          uppercase: true,
          lineHeight: 1,
          letterSpacing: 0,
        },
      ],
    });
  });

  it("leaves out what it does not know, and names an unnamed template", () => {
    const e = ok(extractFields(page([textBox("{{date}}")])));
    const f = buildTemplateFile(e, { name: " ", postType: "general" });
    expect(f.name).toBe("Canva template");
    expect("background" in f).toBe(false);
    expect("fontFamily" in (f.fields[0] ?? {})).toBe(false);
    expect("color" in (f.fields[0] ?? {})).toBe(false);
  });
});

describe("photo and sponsors areas", () => {
  const word = (token: string, o: Parameters<typeof textBox>[1] = {}) =>
    textBox(token, { align: undefined, ...o } as never);

  it("takes the rectangle a photo field sits on as its area, and not as a panel", () => {
    const r = ok(
      extractFields(
        page([
          rect({
            left: 600,
            top: 100,
            width: 200,
            height: 260,
            colour: "#9aa0a6",
          }),
          textBox("{{player 1 photo}}", {
            left: 600,
            top: 220,
            width: 200,
            height: 30,
            format: { textAlign: "center" },
          }),
        ]),
      ),
    );
    const f = r.fields[0];
    expect(f?.binding).toBe("lineup.1.photo");
    expect([f?.x, f?.y, f?.w, f?.h]).toEqual([600, 100, 200, 260]);
    expect(r.panels).toEqual([]);
    expect(r.surfaces.map((s) => s.use)).toEqual(["area"]);
  });

  it("scales the area with the page", () => {
    const r = ok(
      extractFields(
        page(
          [
            rect({
              left: 300,
              top: 50,
              width: 100,
              height: 130,
              colour: "#9aa0a6",
            }),
            textBox("{{player 2 photo}}", {
              left: 300,
              top: 100,
              width: 100,
              height: 20,
              format: { textAlign: "center" },
            }),
          ],
          { width: 540, height: 540 },
        ),
      ),
    );
    const f = r.fields[0];
    expect([f?.x, f?.y, f?.w, f?.h]).toEqual([600, 100, 200, 260]);
  });

  it("uses the smallest rectangle when two stack up", () => {
    const r = ok(
      extractFields(
        page([
          rect({ left: 0, top: 0, width: 900, height: 900, colour: "#eeeeee" }),
          rect({
            left: 600,
            top: 100,
            width: 200,
            height: 200,
            colour: "#9aa0a6",
          }),
          textBox("{{sponsors}}", {
            left: 600,
            top: 180,
            width: 200,
            height: 30,
            format: { textAlign: "center" },
          }),
        ]),
      ),
    );
    expect(r.fields[0]?.w).toBe(200);
    // The bigger rectangle is still free to be a panel.
    expect(r.surfaces.map((s) => s.use)).toEqual(["panel", "area"]);
  });

  it("falls back to the text box width when nothing is under it", () => {
    const photo = ok(
      extractFields(
        page([word("{{player 3 photo}}", { left: 100, top: 100, width: 240 })]),
      ),
    );
    expect(photo.fields[0]?.h).toBe(240);
    const strip = ok(
      extractFields(
        page([word("{{sponsors}}", { left: 100, top: 900, width: 800 })]),
      ),
    );
    expect(strip.fields[0]?.h).toBe(160);
  });

  it("leaves ordinary text alone: no height", () => {
    const r = ok(extractFields(page([textBox("{{player 1}}")])));
    expect(r.fields[0]?.h).toBeNull();
  });

  it("does not take the whole-page background as an area", () => {
    const r = ok(
      extractFields(
        page([
          rect({ width: 1080, height: 1080, colour: "#112233" }),
          textBox("{{sponsors}}", { left: 100, top: 900, width: 800 }),
        ]),
      ),
    );
    expect(r.fields[0]?.h).toBe(160);
    expect(r.surfaces.map((s) => s.use)).toEqual(["background"]);
  });
});

describe("free-standing pictures and page counts", () => {
  const words = textBox("{{player 1}}", { top: 100, left: 40, width: 300 });

  it("keeps a picture nothing is written on, at its own place", () => {
    const r = ok(
      extractFields(
        page([
          rect({
            left: 700,
            top: 150,
            width: 300,
            height: 700,
            media: "image",
            imageRef: "batter",
          }),
          words,
        ]),
      ),
    );
    expect(r.pictures).toEqual([
      {
        imageRef: "batter",
        box: { x: 700, y: 150, w: 300, h: 700, rotation: 0 },
      },
    ]);
    expect(r.surfaces.map((s) => s.use)).toEqual(["picture"]);
    expect(r.panels).toEqual([]);
  });

  it("scales it with the page and keeps its turn", () => {
    const r = ok(
      extractFields(
        page(
          [
            rect({
              left: 350,
              top: 75,
              width: 150,
              height: 350,
              rotation: 10,
              media: "image",
              imageRef: "batter",
            }),
            words,
          ],
          { width: 540, height: 540 },
        ),
      ),
    );
    expect(r.pictures[0]?.box).toEqual({
      x: 700,
      y: 150,
      w: 300,
      h: 700,
      rotation: 10,
    });
  });

  it("leaves out a picture with no id, one in a turned group, and the page background", () => {
    const r = ok(
      extractFields(
        page([
          rect({ width: 1080, height: 1080, media: "image", imageRef: "bg" }),
          rect({
            left: 700,
            top: 150,
            width: 300,
            height: 700,
            media: "image",
          }),
          group(
            [
              rect({
                left: 10,
                top: 10,
                width: 200,
                height: 200,
                media: "image",
                imageRef: "tilted",
              }),
            ],
            { rotation: 20 },
          ),
          words,
        ]),
      ),
    );
    expect(r.pictures).toEqual([]);
    expect(r.backgroundRef).toBe("bg");
  });

  it("keeps at most four", () => {
    const six = Array.from({ length: 6 }, (_, i) =>
      rect({
        left: 600,
        top: 50 + i * 150,
        width: 100,
        height: 100,
        media: "image",
        imageRef: `p${i}`,
      }),
    );
    const r = ok(extractFields(page([...six, words])));
    expect(r.pictures.map((p) => p.imageRef)).toEqual(["p0", "p1", "p2", "p3"]);
  });

  it("does not take a picture a panel already is", () => {
    const r = ok(
      extractFields(
        page([
          rect({
            left: 30,
            top: 60,
            width: 400,
            height: 400,
            media: "image",
            imageRef: "paper",
          }),
          words,
        ]),
      ),
    );
    expect(r.pictures).toEqual([]);
    expect(r.panels[0]?.imageRef).toBe("paper");
  });

  it("counts what Canva lists", () => {
    const r = ok(
      extractFields(
        page([
          textBox("a"),
          textBox("{{date}}"),
          rect({ colour: "#112233" }),
          shape(),
          group([textBox("b")]),
        ]),
      ),
    );
    expect(r.counts).toEqual({
      text: 3,
      rects: 1,
      shapes: 1,
      groups: 1,
      other: 0,
    });
  });
});

describe("placeholder words typed without the braces", () => {
  it("warns that CLUB LOGO is plain text, and how to fix it", () => {
    const r = ok(
      extractFields(
        page([
          textBox("CLUB LOGO"),
          textBox("{{player 1}}"),
          textBox("Sponsors"),
        ]),
      ),
    );
    expect(r.warnings).toEqual([
      "“CLUB LOGO” is plain text, so BetterCricket prints those words. To fill it in automatically, type {{club logo}} instead, or use the Add buttons.",
      "“Sponsors” is plain text, so BetterCricket prints those words. To fill it in automatically, type {{sponsors}} instead, or use the Add buttons.",
    ]);
    expect(r.texts.map((t) => t.text)).toEqual(["CLUB LOGO", "Sponsors"]);
  });

  it("does not warn about ordinary headings or a real token", () => {
    const r = ok(
      extractFields(
        page([
          textBox("LINE UP"),
          textBox("{{club logo}}"),
          textBox("North Perth Cricket Club"),
        ]),
      ),
    );
    expect(r.warnings).toEqual([]);
  });
});
