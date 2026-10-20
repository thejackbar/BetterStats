import type { DesignEditing } from "@canva/design";
import {
  ExportBlocked,
  PICTURE_LIMIT_BYTES,
  exportTemplate,
  type ExportDeps,
} from "../exportFlow";
import type { ElementLike } from "../types";
import { group, page, rect, textBox } from "./fakePage";

type Opts = Partial<{
  fonts: { ref: string; name: string }[];
  /** Per image id: bytes to return, or an error to throw. */
  images: Record<string, number | Error>;
  dims: { width: number; height: number };
}>;

function harness(elements: ElementLike[], o: Opts = {}) {
  const p = page(elements, o.dims);
  const log: string[] = [];
  let syncs = 0;
  const deps: ExportDeps = {
    inPage: async (cb) => {
      await cb({
        page: p,
        helpers: {},
        sync: async () => {
          syncs++;
        },
      } as unknown as DesignEditing.CurrentPageSession);
    },
    fetchImage: async (ref, use) => {
      log.push(`image ${ref} ${use}`);
      const r = o.images?.[ref] ?? 1234;
      if (r instanceof Error) {
        throw r;
      }
      return { dataUrl: `data:image/png;base64,${ref}`, bytes: r };
    },
    lookupFonts: async () => o.fonts ?? [],
  };
  return { deps, log, syncs: () => syncs };
}

const boxes = () => [
  textBox("LINE UP"),
  textBox("{{player 1}}", { top: 300, left: 90, width: 600 }),
  textBox("{{opponent}}", { top: 100, left: 90 }),
];

const lineup = { name: "LineUp", postType: "lineup" } as const;

describe("exportTemplate", () => {
  it("builds the file from the page and touches nothing", async () => {
    const h = harness(boxes());
    const out = await exportTemplate(h.deps, lineup);
    expect(out.fieldCount).toBe(2);
    expect(out.textCount).toBe(1);
    expect(out.file.name).toBe("LineUp");
    expect(out.file.postType).toBe("lineup");
    expect(out.file.background).toBeUndefined();
    expect(out.file.fields.map((f) => f.token)).toEqual([
      "player 1",
      "opponent",
    ]);
    expect(out.file.texts?.map((t) => t.text)).toEqual(["LINE UP"]);
    // The page is only read: no save, no picture asked for.
    expect(h.syncs()).toBe(0);
    expect(h.log).toEqual([]);
    expect(out.background).toBe(false);
    expect(out.pictureProblems).toEqual([]);
  });

  it("writes the post type into the file", async () => {
    const h = harness([textBox("{{opponent}}")]);
    const out = await exportTemplate(h.deps, {
      name: "x",
      postType: "general",
    });
    expect(out.file.postType).toBe("general");
  });

  it("carries the roles, not only the designer's values", async () => {
    const els = [
      textBox("{{player 1}}", { format: { color: "#ffffff", fontSize: 44 } }),
      textBox("{{date}}", {
        format: { color: "#e63946", fontWeight: "bold", fontSize: 30 },
      }),
    ];
    const out = await exportTemplate(harness(els).deps, lineup);
    expect(out.file.fields.map((f) => [f.colorRole, f.fontRole])).toEqual([
      ["ink", "body"],
      ["accent", "display"],
    ]);
    expect(out.file.fields[0]?.color).toBe("#ffffff");
  });

  it("lists a box it left out, without refusing", async () => {
    const els = [textBox("{{player 1}}"), textBox("vs {{opponent}}")];
    const out = await exportTemplate(harness(els).deps, lineup);
    expect(out.fieldCount).toBe(1);
    expect(out.skipped.map((s) => s.reason)).toEqual(["mixed"]);
  });

  it("reads a locked box", async () => {
    const els = [textBox("{{player 1}}", { locked: true })];
    const out = await exportTemplate(harness(els).deps, lineup);
    expect(out.fieldCount).toBe(1);
  });

  it("explains a page with no fields", async () => {
    const err = await exportTemplate(harness([textBox("LINE UP")]).deps, {
      name: "x",
      postType: "general",
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ExportBlocked);
    expect((err as Error).message).toMatch(/no fields/);
  });

  it("names the fonts it can", async () => {
    const els = [textBox("{{player 1}}", { format: { fontRef: "f1" } })];
    const h = harness(els, { fonts: [{ ref: "f1", name: "Anton" }] });
    const out = await exportTemplate(h.deps, lineup);
    expect(out.file.fields[0]?.fontFamily).toBe("Anton");
  });

  describe("the post type", () => {
    it("refuses a line up with no player place", async () => {
      const els = [textBox("{{opponent}}"), textBox("{{date}}")];
      const err = await exportTemplate(harness(els).deps, lineup).catch(
        (e: unknown) => e,
      );
      expect(err).toBeInstanceOf(ExportBlocked);
      expect((err as Error).message).toMatch(/at least one player place/);
    });

    it("accepts the same page as another kind of post", async () => {
      const els = [textBox("{{opponent}}"), textBox("{{date}}")];
      const out = await exportTemplate(harness(els).deps, {
        name: "x",
        postType: "general",
      });
      expect(out.file.postType).toBe("general");
    });

    it("counts a player's first name or role as a player place", async () => {
      const els = [textBox("{{player 1 first}}")];
      const out = await exportTemplate(harness(els).deps, lineup);
      expect(out.fieldCount).toBe(1);
    });
  });

  describe("photo and sponsors areas", () => {
    it("writes the area's box into the file and does not draw the marker as a panel", async () => {
      const els = [
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
          format: { textAlign: "center" },
        }),
        textBox("{{sponsors}}", { left: 100, top: 900, width: 800 }),
        textBox("{{player 1}}"),
      ];
      const out = await exportTemplate(harness(els).deps, lineup);
      const photo = out.file.fields.find((f) => f.token === "player 1 photo");
      expect([photo?.x, photo?.y, photo?.w, photo?.h]).toEqual([
        600, 100, 200, 260,
      ]);
      const strip = out.file.fields.find((f) => f.token === "sponsors");
      expect(strip?.h).toBe(160);
      const name = out.file.fields.find((f) => f.token === "player 1");
      expect(name).not.toHaveProperty("h");
      expect(out.file.panels).toBeUndefined();
    });
  });

  describe("the design's own pictures", () => {
    const maroon = (extra: Record<string, unknown> = {}) =>
      rect({
        top: 100,
        left: 50,
        width: 400,
        height: 800,
        rotation: 90,
        media: "image",
        imageRef: "paper",
        ...extra,
      });

    it("carries a picture that covers the page as the background", async () => {
      const els = [
        rect({ width: 1080, height: 1080, media: "image", imageRef: "bg" }),
        textBox("{{player 1}}"),
      ];
      const h = harness(els);
      const out = await exportTemplate(h.deps, lineup);
      expect(h.log).toEqual(["image bg background"]);
      expect(out.file.background).toBe("data:image/png;base64,bg");
      expect(out.background).toBe(true);
    });

    it("leaves a solid page colour to BetterCricket", async () => {
      const els = [
        rect({ width: 1080, height: 1080, colour: "#112233" }),
        textBox("{{player 1}}"),
      ];
      const h = harness(els);
      const out = await exportTemplate(h.deps, lineup);
      expect(h.log).toEqual([]);
      expect(out.file.background).toBeUndefined();
    });

    it("keeps a picture panel as a picture at its own box and turn", async () => {
      // The words sit on the turned paper.
      const els = [maroon(), textBox("{{player 1}}", { top: 400, left: 60 })];
      const h = harness(els);
      const out = await exportTemplate(h.deps, lineup);
      expect(h.log).toEqual(["image paper panel"]);
      const panel = out.file.panels?.[0];
      expect(panel?.image).toBe("data:image/png;base64,paper");
      expect(panel?.box).toEqual({
        x: 50,
        y: 100,
        w: 400,
        h: 800,
        rotation: 90,
      });
      expect(out.panelPictures).toBe(1);
    });

    it("scales the box to the 1080 space", async () => {
      const els = [
        maroon({ top: 50, left: 25, width: 200, height: 400, rotation: 0 }),
        textBox("{{player 1}}", { top: 100, left: 40 }),
      ];
      const h = harness(els, { dims: { width: 540, height: 540 } });
      const out = await exportTemplate(h.deps, lineup);
      expect(out.file.panels?.[0]?.box).toEqual({
        x: 50,
        y: 100,
        w: 400,
        h: 800,
        rotation: 0,
      });
    });

    it("fetches a picture once when two things share it", async () => {
      const els = [
        rect({ width: 1080, height: 1080, media: "image", imageRef: "same" }),
        maroon({ imageRef: "same" }),
        textBox("{{player 1}}", { top: 400, left: 60 }),
      ];
      const h = harness(els);
      await exportTemplate(h.deps, lineup);
      expect(h.log).toEqual(["image same background"]);
    });

    it("still makes the file, and says so, when a picture cannot be fetched", async () => {
      const els = [maroon(), textBox("{{player 1}}", { top: 400, left: 60 })];
      const h = harness(els, {
        images: {
          paper: new Error("Canva would not give the app this picture."),
        },
      });
      const out = await exportTemplate(h.deps, lineup);
      expect(out.pictureProblems).toEqual([
        "Panel 1: Canva would not give the app this picture.",
      ]);
      const panel = out.file.panels?.[0];
      expect(panel?.image).toBeUndefined();
      expect(panel?.box).toBeUndefined();
      // The panel itself is still there, to be drawn as a box.
      expect(panel?.source).toBe("picture");
      expect(out.panelPictures).toBe(0);
    });

    it("leaves out a picture over BetterCricket's limit, and says so", async () => {
      const els = [
        rect({ width: 1080, height: 1080, media: "image", imageRef: "huge" }),
        textBox("{{player 1}}"),
      ];
      const h = harness(els, { images: { huge: PICTURE_LIMIT_BYTES + 1 } });
      const out = await exportTemplate(h.deps, lineup);
      expect(out.file.background).toBeUndefined();
      expect(out.pictureProblems[0]).toMatch(/Background: .*5 MB/);
    });

    it("does not ask for a picture it cannot place (no id from Canva)", async () => {
      const els = [maroon({ imageRef: undefined }), textBox("{{player 1}}")];
      const h = harness(els);
      const out = await exportTemplate(h.deps, lineup);
      expect(h.log).toEqual([]);
      expect(out.file.panels?.[0]?.image).toBeUndefined();
    });

    it("leaves a picture in a rotated group alone", async () => {
      const els = [
        group([maroon()], { rotation: 15 }),
        textBox("{{player 1}}", { top: 400, left: 60 }),
      ];
      const h = harness(els);
      await exportTemplate(h.deps, lineup);
      expect(h.log).toEqual([]);
    });
  });
});

describe("limits", () => {
  it("knows BetterCricket's picture limit", () => {
    expect(PICTURE_LIMIT_BYTES).toBe(5 * 1024 * 1024);
  });
});
