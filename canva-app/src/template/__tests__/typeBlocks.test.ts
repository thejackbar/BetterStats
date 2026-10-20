import typeCases from "../type-cases.json";
import { TYPE_BLOCKS, typeFieldTokens } from "../typeBlocks";
import { hasTypeField, isPostAreaBinding, type PostType } from "../postFields";
import { bindFromToken } from "../tokens";

const page = { width: 1080, height: 1080 };
const types = Object.keys(TYPE_BLOCKS) as PostType[];
const tokenOf = (text: string) => text.replace(/^\{\{|\}\}$/g, "");

describe("which words belong to which post type (shared with the BetterCricket editor)", () => {
  it.each(typeCases)("$type with $binds -> $ok", ({ type, binds, ok }) => {
    expect(hasTypeField(type as PostType, binds)).toBe(ok);
  });
});

describe("the ready-made blocks for each post type", () => {
  it("covers every post type except the line up and other posts", () => {
    expect(types.sort()).toEqual(
      [
        "announcement",
        "events",
        "fixtures",
        "milestones",
        "motm",
        "result",
        "results",
        "toss",
        "totw",
      ].sort(),
    );
  });

  for (const type of [
    "fixtures",
    "results",
    "result",
    "motm",
    "totw",
    "milestones",
    "announcement",
    "toss",
    "events",
  ] as PostType[]) {
    for (const block of TYPE_BLOCKS[type] ?? []) {
      const counts = block.count
        ? [block.count.min, block.count.start, block.count.max]
        : [1];
      it.each(counts)(
        `${type} ${block.id}: every word is a field of that type (%i rows)`,
        (n) => {
          const spec = block.build(page, n);
          expect(spec.boxes.length).toBeGreaterThan(0);
          const bound = spec.boxes
            .filter((b) => b.text.startsWith("{{"))
            .map((b) => bindFromToken(tokenOf(b.text)));
          expect(bound.length).toBeGreaterThan(0);
          expect(bound.every((b) => b != null)).toBe(true);
          expect(hasTypeField(type, bound)).toBe(true);
        },
      );

      it.each(counts)(
        `${type} ${block.id}: boxes stay on the page and readable (%i rows)`,
        (n) => {
          const spec = block.build(page, n);
          for (const b of spec.boxes) {
            expect(b.fontSize).toBeGreaterThanOrEqual(10);
            expect(b.left).toBeGreaterThanOrEqual(0);
            expect(b.left + b.width).toBeLessThanOrEqual(page.width);
            expect(b.top).toBeGreaterThanOrEqual(0);
            expect(b.top + b.fontSize).toBeLessThanOrEqual(page.height);
          }
        },
      );
    }
  }

  it("asks for as many rows as the post can hold", () => {
    const max = (type: PostType) => TYPE_BLOCKS[type]?.map((b) => b.count?.max);
    expect(max("fixtures")).toEqual([8]);
    expect(max("totw")).toEqual([15]);
    expect(max("milestones")).toEqual([8]);
  });

  it("gives a photo area its marker and a photo word", () => {
    const spec = TYPE_BLOCKS.announcement?.[0]?.build(page, 1);
    expect(spec?.rects?.length).toBe(1);
    expect(spec?.boxes.some((b) => b.text === "{{announcement photo}}")).toBe(
      true,
    );
  });
});

describe("the single-field picker for each post type", () => {
  it.each([
    "fixtures",
    "results",
    "result",
    "motm",
    "totw",
    "milestones",
    "announcement",
    "toss",
    "events",
  ] as PostType[])("%s: every option is a word BetterCricket knows", (type) => {
    const tokens = typeFieldTokens(type);
    expect(tokens.length).toBeGreaterThan(2);
    expect(tokens.filter((t) => bindFromToken(t) == null)).toEqual([]);
    expect(new Set(tokens).size).toBe(tokens.length);
  });

  it("offers photos for the types that have them", () => {
    expect(
      typeFieldTokens("totw").filter((t) =>
        isPostAreaBinding(bindFromToken(t)),
      ),
    ).toHaveLength(15);
  });

  it("has nothing for the line up and other posts (they have their own)", () => {
    expect(typeFieldTokens("lineup")).toEqual([]);
    expect(typeFieldTokens("general")).toEqual([]);
  });
});
