import { lineUpBlock, sponsorsBlock } from "../blocks";
import { InsertError, insertBlock } from "../insert";
import { must } from "./fakePage";
import { fakeSession } from "./fakeSession";

const spec = lineUpBlock({ width: 1080, height: 1080 }, 3);

describe("insertBlock", () => {
  it("adds separate boxes and saves once, by default", async () => {
    const { session, calls } = fakeSession();
    const r = await insertBlock(session, spec);
    expect(r).toEqual({ added: 4, grouped: false });
    expect(calls.created).toHaveLength(4);
    expect(calls.grouped).toHaveLength(0);
    expect(calls.syncs).toBe(1);
  });

  it("groups the boxes when asked", async () => {
    const { session, calls } = fakeSession();
    const r = await insertBlock(session, spec, { group: true });
    expect(r).toEqual({ added: 4, grouped: true });
    expect(calls.grouped).toHaveLength(1);
    expect(calls.grouped[0]).toHaveLength(4);
    expect(calls.syncs).toBe(1);
  });

  it("does not try to group a single box", async () => {
    const { session, calls } = fakeSession();
    const one = { name: "one", boxes: spec.boxes.slice(0, 1) };
    const r = await insertBlock(session, one, { group: true });
    expect(r).toEqual({ added: 1, grouped: false });
    expect(calls.grouped).toHaveLength(0);
  });

  it("sends the text, size, colour, weight and position Canva needs", async () => {
    const { session, calls } = fakeSession();
    await insertBlock(session, spec);
    const first = calls.created[0] as {
      top: number;
      left: number;
      width: number;
      text: {
        regions: { text: string; formatting: Record<string, unknown> }[];
      };
    };
    const heading = must(spec.boxes[0]);
    expect(first).toMatchObject({
      top: heading.top,
      left: heading.left,
      width: heading.width,
    });
    expect(first.text.regions[0]).toEqual({
      text: "LINE UP",
      formatting: {
        fontSize: heading.fontSize,
        color: heading.color,
        fontWeight: "bold",
        textAlign: "start",
      },
    });
    const row = calls.created[1] as typeof first;
    expect(row.text.regions[0]?.text).toBe("{{player 1}}");
    expect(row.text.regions[0]?.formatting.fontWeight).toBe("normal");
  });

  it("puts the block on top: after the last element, then each after the one before", async () => {
    const { session, calls } = fakeSession({
      existing: [
        { type: "rect", id: "background" },
        { type: "text", id: "title" },
      ],
    });
    await insertBlock(session, spec);
    expect(calls.inserted[0]?.after).toEqual({ type: "text", id: "title" });
    expect(calls.inserted[1]?.after).toEqual({ type: "text", id: "new0" });
    expect(calls.inserted[3]?.after).toEqual({ type: "text", id: "new2" });
  });

  it("starts from nothing on an empty page", async () => {
    const { session, calls } = fakeSession();
    await insertBlock(session, spec);
    expect(calls.inserted[0]?.after).toBeUndefined();
  });

  it("keeps the boxes, loose, and says why when Canva refuses to group them", async () => {
    const { session, calls } = fakeSession({ groupFails: true });
    const r = await insertBlock(session, spec, { group: true });
    expect(r).toMatchObject({ added: 4, grouped: false });
    expect(r.groupError).toMatch(/cannot group/);
    expect(calls.syncs).toBe(1);
  });

  it("names the step when saving fails", async () => {
    const { session } = fakeSession({ syncFails: true });
    const err = await insertBlock(session, spec).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(InsertError);
    expect((err as InsertError).step).toBe("saving to the design");
    expect((err as Error).message).toMatch(
      /stopped while saving to the design: .*internal_error/,
    );
  });

  it("changes nothing on a locked page", async () => {
    const { session, calls } = fakeSession({ locked: true });
    await expect(insertBlock(session, spec)).rejects.toThrow(/locked/);
    expect(calls.created).toHaveLength(0);
    expect(calls.syncs).toBe(0);
  });

  it("changes nothing on a page type apps cannot edit", async () => {
    const { session, calls } = fakeSession({ pageType: "unsupported" });
    await expect(insertBlock(session, spec)).rejects.toThrow(
      /cannot be edited/,
    );
    expect(calls.created).toHaveLength(0);
    expect(calls.syncs).toBe(0);
  });

  it("does not save a half-made block when Canva refuses a box", async () => {
    const { session, calls } = fakeSession({ insertFails: true });
    const err = await insertBlock(session, spec).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(InsertError);
    expect((err as Error).message).toMatch(
      /stopped while adding the boxes: .*would not add/,
    );
    expect(calls.syncs).toBe(0);
    expect(calls.grouped).toHaveLength(0);
  });
});

describe("insertBlock with a marker rectangle", () => {
  it("adds the rectangle first so the words sit on top, and counts only the text boxes", async () => {
    const { session, calls } = fakeSession();
    const r = await insertBlock(
      session,
      sponsorsBlock({ width: 1080, height: 1080 }),
    );
    expect(r).toEqual({ added: 1, grouped: false });
    expect(calls.created).toHaveLength(2);
    expect(calls.created[0]).toHaveProperty("rect");
    const rect = (calls.created[0] as { rect: Record<string, unknown> }).rect;
    expect(rect.fill).toEqual({
      colorContainer: { type: "solid", color: "#9aa0a6" },
    });
    expect(calls.created[1]).toHaveProperty("text");
    expect(calls.syncs).toBe(1);
  });
});
