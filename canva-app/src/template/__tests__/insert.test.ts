import { lineUpBlock } from "../blocks";
import { insertBlock } from "../insert";
import { must } from "./fakePage";
import { fakeSession } from "./fakeSession";

const spec = lineUpBlock({ width: 1080, height: 1080 }, 3);

describe("insertBlock", () => {
  it("adds every box, groups them, and saves once", async () => {
    const { session, calls } = fakeSession();
    const r = await insertBlock(session, spec);
    expect(r).toEqual({ added: 4, grouped: true });
    expect(calls.created).toHaveLength(4);
    expect(calls.grouped).toHaveLength(1);
    expect(calls.grouped[0]).toHaveLength(4);
    expect(calls.syncs).toBe(1);
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

  it("keeps the boxes, loose, when Canva refuses to group them", async () => {
    const { session, calls } = fakeSession({ groupFails: true });
    const r = await insertBlock(session, spec);
    expect(r).toEqual({ added: 4, grouped: false });
    expect(calls.syncs).toBe(1);
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
    await expect(insertBlock(session, spec)).rejects.toThrow(/would not add/);
    expect(calls.syncs).toBe(0);
    expect(calls.grouped).toHaveLength(0);
  });
});
