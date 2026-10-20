import type { DesignEditing, ExportResponse } from "@canva/design";
import {
  type ExportOutcome,
  ExportBlocked,
  PICTURE_LIMIT_BYTES,
  RestoreFailed,
  exportTemplate,
  restoreHidden,
  type ExportDeps,
} from "../exportFlow";
import type { Hidden } from "../hide";
import type { ElementLike, TextElementLike } from "../types";
import { group, page, textBox } from "./fakePage";

type Opts = Partial<{
  syncFailsAt: number[];
  exportResult: ExportResponse | Error;
  fetch: "ok" | Error;
  fonts: { ref: string; name: string }[];
}>;

// Live elements shared by every "session", so a change in one is seen by the next.
function harness(elements: ElementLike[], o: Opts = {}) {
  const p = page(elements);
  const log: string[] = [];
  let syncs = 0;
  const atExport: number[] = [];
  const deps: ExportDeps = {
    inPage: async (cb) => {
      const session = {
        page: p,
        helpers: {},
        sync: async () => {
          syncs++;
          log.push(`sync${syncs}`);
          if (o.syncFailsAt?.includes(syncs)) {
            throw new Error("[internal_error]: sync failed");
          }
        },
      } as unknown as DesignEditing.CurrentPageSession;
      await cb(session);
    },
    requestExport: async () => {
      log.push("export");
      for (const el of elements) {
        if (el.type === "text") {
          atExport.push((el as TextElementLike).transparency);
        }
      }
      const r = o.exportResult ?? {
        status: "completed",
        exportBlobs: [{ url: "https://export.example/design.png" }],
      };
      if (r instanceof Error) {
        throw r;
      }
      return r;
    },
    fetchPicture: async (url) => {
      log.push(`fetch ${url}`);
      if (o.fetch instanceof Error) {
        throw o.fetch;
      }
      return { dataUrl: "data:image/png;base64,AAAA", bytes: 1234 };
    },
    lookupFonts: async () => o.fonts ?? [],
  };
  return { deps, log, atExport, syncs: () => syncs };
}

// Narrow an outcome, failing the test loudly if it was a different one.
function asDone(out: ExportOutcome) {
  if (out.status !== "done") {
    throw new Error(`expected a finished export, got ${out.status}`);
  }
  return out;
}
function asNoPicture(out: ExportOutcome) {
  if (out.status !== "no_picture") {
    throw new Error(`expected an export without a picture, got ${out.status}`);
  }
  return out;
}

const boxes = () => [
  textBox("LINE UP"),
  textBox("{{player 1}}", { top: 300, left: 90, width: 600, transparency: 0 }),
  textBox("{{opponent}}", { top: 100, left: 90, transparency: 0.25 }),
];
const transparencies = (els: ElementLike[]) =>
  els.map((e) => (e as TextElementLike).transparency);

describe("exportTemplate", () => {
  it("hides the words, exports, puts the words back, and builds the file", async () => {
    const els = boxes();
    const h = harness(els, { fonts: [] });
    const out = await exportTemplate(h.deps, {
      name: "LineUp",
      withPicture: true,
    });
    const done = asDone(out);
    // Order of events: hide and save, export, restore and save, fetch the picture.
    expect(h.log).toEqual([
      "sync1",
      "export",
      "sync2",
      "fetch https://export.example/design.png",
    ]);
    // While Canva exported, both field boxes were invisible and the heading was not.
    expect(h.atExport).toEqual([0, 1, 1]);
    // Afterwards everything is exactly as it was.
    expect(transparencies(els)).toEqual([0, 0, 0.25]);
    expect(done.fieldCount).toBe(2);
    expect(done.textCount).toBe(1);
    expect(done.pictureBytes).toBe(1234);
    expect(done.file.background).toBe("data:image/png;base64,AAAA");
    expect(done.file.name).toBe("LineUp");
    expect(done.file.fields.map((f) => f.token)).toEqual([
      "player 1",
      "opponent",
    ]);
  });

  it("puts the words back when the export is cancelled", async () => {
    const els = boxes();
    const h = harness(els, { exportResult: { status: "aborted" } });
    const out = await exportTemplate(h.deps, { name: "x", withPicture: true });
    expect(out).toEqual({ status: "aborted" });
    expect(transparencies(els)).toEqual([0, 0, 0.25]);
    expect(h.log).toEqual(["sync1", "export", "sync2"]);
  });

  it("puts the words back when Canva fails the export, and says so", async () => {
    const els = boxes();
    const h = harness(els, {
      exportResult: new Error("[internal_error]: boom"),
    });
    await expect(
      exportTemplate(h.deps, { name: "x", withPicture: true }),
    ).rejects.toThrow(/could not export the picture: .*boom/);
    expect(transparencies(els)).toEqual([0, 0, 0.25]);
    expect(h.log).toEqual(["sync1", "export", "sync2"]);
  });

  it("still gives the fields when the picture cannot be fetched", async () => {
    const els = boxes();
    const h = harness(els, {
      fetch: new Error("blocked by the app's security policy"),
    });
    const out = await exportTemplate(h.deps, { name: "x", withPicture: true });
    expect(transparencies(els)).toEqual([0, 0, 0.25]);
    const np = asNoPicture(out);
    expect(np.reason).toMatch(/security policy/);
    expect(np.pictureUrl).toBe("https://export.example/design.png");
    expect(np.file.background).toBeUndefined();
    expect(np.fieldCount).toBe(2);
  });

  it("reports a missing picture", async () => {
    const h = harness(boxes(), {
      exportResult: { status: "completed", exportBlobs: [] },
    });
    const out = await exportTemplate(h.deps, { name: "x", withPicture: true });
    expect(asNoPicture(out).pictureUrl).toBeNull();
  });

  it("names the fonts it found in the file", async () => {
    const els = [textBox("{{player 1}}", { format: { fontRef: "f1" } })];
    const h = harness(els, { fonts: [{ ref: "f1", name: "Anton" }] });
    const out = await exportTemplate(h.deps, { name: "x", withPicture: true });
    expect(out.status === "done" && out.file.fields[0]?.fontFamily).toBe(
      "Anton",
    );
  });

  it("tells the caller what was hidden before the export starts", async () => {
    const h = harness(boxes());
    const seen: Hidden[][] = [];
    await exportTemplate(h.deps, { name: "x", withPicture: true }, (hidden) => {
      seen.push(hidden);
      expect(h.log).not.toContain("export");
    });
    expect(seen).toHaveLength(1);
    expect(seen[0]).toHaveLength(2);
  });

  describe("refuses, and changes nothing, when the picture would be wrong", () => {
    const refused = async (els: ElementLike[]) => {
      const h = harness(els);
      const err = await exportTemplate(h.deps, {
        name: "x",
        withPicture: true,
      }).catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ExportBlocked);
      expect(h.log).toEqual([]);
      return err as ExportBlocked;
    };

    it("on a page with no fields", async () => {
      const err = await refused([textBox("LINE UP")]);
      expect(err.message).toMatch(/no fields/);
    });

    it("when a box mixes a token with other words", async () => {
      const els = [textBox("{{player 1}}"), textBox("vs {{opponent}}")];
      const err = await refused(els);
      expect(err.skipped).toEqual([
        { reason: "mixed", text: "vs {{opponent}}" },
      ]);
      expect(transparencies(els)).toEqual([0, 0]);
    });

    it("when a field box is locked (it could not be hidden)", async () => {
      const els = [
        textBox("{{player 1}}"),
        textBox("{{date}}", { locked: true }),
      ];
      const err = await refused(els);
      expect(err.skipped.map((s) => s.reason)).toEqual(["locked"]);
      expect(transparencies(els)).toEqual([0, 0]);
    });

    it("when a field box is in a rotated group", async () => {
      const err = await refused([
        textBox("{{player 1}}"),
        group([textBox("{{date}}")], { rotation: 20 }),
      ]);
      expect(err.skipped.map((s) => s.reason)).toEqual(["rotated_group"]);
    });
  });

  it("puts the words back if saving the hide fails, and reports the failure", async () => {
    const els = boxes();
    const h = harness(els, { syncFailsAt: [1] });
    await expect(
      exportTemplate(h.deps, { name: "x", withPicture: true }),
    ).rejects.toThrow(/sync failed/);
    expect(transparencies(els)).toEqual([0, 0, 0.25]);
    expect(h.log).not.toContain("export");
  });

  it("says the words are still hidden, and what to press, when it cannot put them back", async () => {
    const els = boxes();
    const h = harness(els, { syncFailsAt: [2] });
    const err = await exportTemplate(h.deps, {
      name: "x",
      withPicture: true,
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(RestoreFailed);
    expect((err as RestoreFailed).message).toMatch(/Restore placeholders/);
    expect((err as RestoreFailed).hidden).toHaveLength(2);
  });

  it("lets a retry restore them later", async () => {
    const els = boxes();
    const h = harness(els, { syncFailsAt: [2] });
    const err = (await exportTemplate(h.deps, {
      name: "x",
      withPicture: true,
    }).catch((e: unknown) => e)) as RestoreFailed;
    // Canva refused the first restore, so the in-memory boxes are back but the
    // design was not saved. A manual restore goes through now.
    await restoreHidden(h.deps.inPage, err.hidden);
    expect(transparencies(els)).toEqual([0, 0, 0.25]);
  });
});

describe("restoreHidden", () => {
  it("does nothing when nothing was hidden", async () => {
    const h = harness(boxes());
    await restoreHidden(h.deps.inPage, []);
    expect(h.log).toEqual([]);
  });
});

describe("limits", () => {
  it("knows BetterCricket's picture limit", () => {
    expect(PICTURE_LIMIT_BYTES).toBe(5 * 1024 * 1024);
  });
});

describe("structure-only export (the default)", () => {
  it("builds the file from the page and touches nothing", async () => {
    const els = boxes();
    const h = harness(els, { fonts: [] });
    const out = asDone(await exportTemplate(h.deps, { name: "LineUp" }));
    expect(out.pictureBytes).toBeNull();
    expect(out.fieldCount).toBe(2);
    expect(out.textCount).toBe(1);
    expect(out.file.background).toBeUndefined();
    expect(out.file.fields.map((f) => f.token)).toEqual([
      "player 1",
      "opponent",
    ]);
    expect(out.file.texts?.map((t) => t.text)).toEqual(["LINE UP"]);
    // No hide, no export dialog, no picture fetch, no save.
    expect(h.log).toEqual([]);
    expect(transparencies(els)).toEqual([0, 0, 0.25]);
  });

  it("carries the roles, not only the designer's values", async () => {
    const els = [
      textBox("{{player 1}}", { format: { color: "#ffffff", fontSize: 44 } }),
      textBox("{{date}}", {
        format: { color: "#e63946", fontWeight: "bold", fontSize: 30 },
      }),
    ];
    const out = asDone(await exportTemplate(harness(els).deps, { name: "x" }));
    expect(out.file.fields.map((f) => [f.colorRole, f.fontRole])).toEqual([
      ["ink", "body"],
      ["accent", "display"],
    ]);
    expect(out.file.fields[0]?.color).toBe("#ffffff");
  });

  it("lists a box it left out, without refusing", async () => {
    const els = [
      textBox("{{player 1}}"),
      textBox("vs {{opponent}}"),
      textBox("{{date}}", { locked: true }),
    ];
    const out = asDone(await exportTemplate(harness(els).deps, { name: "x" }));
    expect(out.fieldCount).toBe(1);
    expect(out.skipped.map((s) => s.reason)).toEqual(["mixed", "locked"]);
  });

  it("explains a page with no fields", async () => {
    const err = await exportTemplate(harness([textBox("LINE UP")]).deps, {
      name: "x",
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ExportBlocked);
    expect((err as Error).message).toMatch(/no fields/);
  });

  it("names the fonts it can", async () => {
    const els = [textBox("{{player 1}}", { format: { fontRef: "f1" } })];
    const h = harness(els, { fonts: [{ ref: "f1", name: "Anton" }] });
    const out = asDone(await exportTemplate(h.deps, { name: "x" }));
    expect(out.file.fields[0]?.fontFamily).toBe("Anton");
  });
});
