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

  it("leaves out and reports a locked box, which could not be hidden", () => {
    const r = ok(extractFields(page([textBox("{{date}}", { locked: true })])));
    expect(r.fields).toEqual([]);
    expect(r.skipped).toEqual([{ reason: "locked", text: "{{date}}" }]);
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

  it("leaves out and reports a box in a locked group", () => {
    const r = ok(
      extractFields(page([group([textBox("{{player 1}}")], { locked: true })])),
    );
    expect(r.fields).toEqual([]);
    expect(r.skipped.map((x) => x.reason)).toEqual(["locked"]);
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
        background: "data:image/png;base64,AAAA",
      }),
    ).toEqual({
      format: "bettercricket-template",
      version: 1,
      name: "LineUp",
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
    const f = buildTemplateFile(e, { name: " " });
    expect(f.name).toBe("Canva template");
    expect("background" in f).toBe(false);
    expect("fontFamily" in (f.fields[0] ?? {})).toBe(false);
    expect("color" in (f.fields[0] ?? {})).toBe(false);
  });
});
