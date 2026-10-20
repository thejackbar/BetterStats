import { describeSurfaces } from "../describe";
import { group, page, rect, shape, textBox } from "./fakePage";

const SIZE = { width: 1080, height: 1080 };

describe("describeSurfaces", () => {
  it("ignores text and describes rects and shapes", () => {
    const out = describeSurfaces(
      page([
        textBox("{{player 1}}"),
        rect({ top: 10, left: 20, width: 300, height: 400, colour: "#7B3B3B" }),
        shape({ top: 50, left: 60, width: 500, height: 700 }),
      ]),
    );
    expect(out.map((s) => s.kind)).toEqual(["rect", "shape"]);
    expect(out[0]).toMatchObject({
      x: 20,
      y: 10,
      w: 300,
      h: 400,
      fill: { kind: "solid", color: "#7b3b3b" },
      fullPage: false,
      rotated: false,
    });
  });

  it("tells a solid colour from a picture, a video and nothing", () => {
    const fills = describeSurfaces(
      page([
        rect({ colour: "#ffffff" }),
        rect({ media: "image" }),
        rect({ media: "video" }),
        rect({}),
      ]),
    ).map((s) => s.fill.kind);
    expect(fills).toEqual(["solid", "image", "video", "none"]);
  });

  it("describes a shape by its paths", () => {
    const [one, many, mixed, pic] = describeSurfaces(
      page([
        shape({ paths: [{ d: "M0 0", colour: "#111111" }] }),
        shape({
          paths: [
            { d: "M0 0", colour: "#111111" },
            { d: "M1 1", colour: "#111111" },
          ],
        }),
        shape({
          paths: [
            { d: "M0 0", colour: "#111111" },
            { d: "M1 1", colour: "#222222" },
          ],
        }),
        shape({ paths: [{ d: "M0 0", media: "image" }] }),
      ]),
    );
    expect(one).toMatchObject({
      paths: 1,
      fill: { kind: "solid", color: "#111111" },
    });
    expect(many).toMatchObject({
      paths: 2,
      fill: { kind: "solid", color: "#111111" },
    });
    expect(mixed).toMatchObject({ paths: 2, fill: { kind: "mixed" } });
    expect(pic).toMatchObject({ paths: 1, fill: { kind: "image" } });
  });

  it("marks an element that covers the page as the background", () => {
    const [bg, panel] = describeSurfaces(
      page(
        [
          rect({ width: 1080, height: 1080, colour: "#ffffff" }),
          rect({ width: 400, height: 900, colour: "#7b3b3b" }),
        ],
        SIZE,
      ),
    );
    expect(bg?.fullPage).toBe(true);
    expect(panel?.fullPage).toBe(false);
  });

  it("adds a group's position to what is inside it", () => {
    const [s] = describeSurfaces(
      page([group([rect({ top: 5, left: 7 })], { top: 100, left: 200 })]),
    );
    expect(s).toMatchObject({ x: 207, y: 105 });
  });

  it("flags a rotated element, and one in a rotated group", () => {
    const out = describeSurfaces(
      page([
        rect({ rotation: 30 }),
        group([rect({})], { rotation: 45 }),
        rect({}),
      ]),
    );
    expect(out.map((s) => s.rotated)).toEqual([true, true, false]);
  });

  it("returns nothing for a page with no shapes", () => {
    expect(describeSurfaces(page([textBox("hi")]))).toEqual([]);
  });
});
