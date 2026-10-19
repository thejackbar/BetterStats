import { hideFields, restoreFields } from "../hide";
import { group, must, page, textBox } from "./fakePage";

describe("hideFields", () => {
  it("makes each field box fully transparent and records what it was", () => {
    const a = textBox("{{player 1}}", { top: 10, left: 20, transparency: 0 });
    const b = textBox("{{date}}", { top: 50, left: 60, transparency: 0.3 });
    const hidden = hideFields(page([a, b]));
    expect([a.transparency, b.transparency]).toEqual([1, 1]);
    expect(hidden).toEqual([
      { token: "player 1", x: 20, y: 10, original: 0 },
      { token: "date", x: 60, y: 50, original: 0.3 },
    ]);
  });

  it("leaves everything else alone", () => {
    const plain = textBox("LINE UP");
    const mixed = textBox("vs {{opponent}}");
    const locked = textBox("{{venue}}", { locked: true });
    const inRotated = textBox("{{round}}");
    const hidden = hideFields(
      page([plain, mixed, locked, group([inRotated], { rotation: 30 })]),
    );
    expect(hidden).toEqual([]);
    expect(
      [plain, mixed, locked, inRotated].map((x) => x.transparency),
    ).toEqual([0, 0, 0, 0]);
  });

  it("hides a box inside a group and records its place on the page", () => {
    const inner = textBox("{{player 1}}", { top: 5, left: 7 });
    const hidden = hideFields(page([group([inner], { top: 100, left: 200 })]));
    expect(inner.transparency).toBe(1);
    expect(hidden).toEqual([
      { token: "player 1", x: 207, y: 105, original: 0 },
    ]);
  });
});

describe("restoreFields", () => {
  it("puts each box back to the transparency it had", () => {
    const a = textBox("{{player 1}}", { top: 10, left: 20 });
    const b = textBox("{{date}}", { top: 50, left: 60, transparency: 0.3 });
    const p = page([a, b]);
    const hidden = hideFields(p);
    expect(restoreFields(p, hidden)).toEqual({ restored: 2, missing: 0 });
    expect([a.transparency, b.transparency]).toEqual([0, 0.3]);
  });

  it("restores a box that was already invisible to invisible, not visible", () => {
    const a = textBox("{{date}}", { transparency: 1 });
    const p = page([a]);
    const hidden = hideFields(p);
    restoreFields(p, hidden);
    expect(a.transparency).toBe(1);
  });

  it("tells two boxes with the same token apart by where they are", () => {
    const top = textBox("{{opponent}}", {
      top: 10,
      left: 10,
      transparency: 0.2,
    });
    const low = textBox("{{opponent}}", {
      top: 400,
      left: 10,
      transparency: 0.6,
    });
    const p = page([top, low]);
    const hidden = hideFields(p);
    restoreFields(p, hidden);
    expect([top.transparency, low.transparency]).toEqual([0.2, 0.6]);
  });

  it("restores a box inside a group", () => {
    const inner = textBox("{{player 1}}", {
      top: 5,
      left: 7,
      transparency: 0.4,
    });
    const p = page([group([inner], { top: 100, left: 200 })]);
    const hidden = hideFields(p);
    restoreFields(p, hidden);
    expect(inner.transparency).toBe(0.4);
  });

  it("counts a box that has gone, and still restores the rest", () => {
    const a = textBox("{{player 1}}", { top: 10, left: 20 });
    const b = textBox("{{date}}", { top: 50, left: 60 });
    const hidden = hideFields(page([a, b]));
    const result = restoreFields(page([b]), hidden);
    expect(result).toEqual({ restored: 1, missing: 1 });
    expect(must(b).transparency).toBe(0);
  });

  it("does not touch a box that has moved, rather than guess", () => {
    const a = textBox("{{player 1}}", { top: 10, left: 20 });
    const hidden = hideFields(page([a]));
    a.top = 300;
    const result = restoreFields(page([a]), hidden);
    expect(result).toEqual({ restored: 0, missing: 1 });
    expect(a.transparency).toBe(1);
  });
});
