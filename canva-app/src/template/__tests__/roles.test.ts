import { colorRole, fontRole, hsl } from "../roles";

describe("colorRole", () => {
  it.each([
    ["#ffffff", "ink"],
    ["#fafafa", "ink"],
    ["#000000", "ink"],
    ["#1a1a1a", "ink"],
    ["#222222", "ink"],
    ["#808080", "ink"],
    ["#c4c4c4", "ink"],
    ["#ffe14d", "accent"],
    ["#ffdd1a", "accent"],
    ["#e63946", "accent"],
    ["#2a9d8f", "accent"],
    ["#7b3b3b", "accent"],
    ["#0b3d91", "accent"],
  ])("%s is %s", (hex, role) => {
    expect(colorRole(hex)).toBe(role);
  });

  it("treats a colour it cannot read, or none, as ink", () => {
    expect(colorRole(null)).toBe("ink");
    expect(colorRole("red")).toBe("ink");
    expect(colorRole("#fff")).toBe("ink");
  });

  it("is case-insensitive", () => {
    expect(colorRole("#FFE14D")).toBe("accent");
  });
});

describe("hsl", () => {
  it("reads saturation and lightness", () => {
    expect(hsl("#ffffff")).toEqual({ s: 0, l: 1 });
    expect(hsl("#000000")).toEqual({ s: 0, l: 0 });
    expect(hsl("#ff0000")).toEqual({ s: 1, l: 0.5 });
    expect(hsl("nope")).toBeNull();
  });
});

describe("fontRole", () => {
  it("uses the display font for bold or large words", () => {
    expect(fontRole(true, 20)).toBe("display");
    expect(fontRole(false, 56)).toBe("display");
    expect(fontRole(false, 120)).toBe("display");
  });
  it("uses the body font for small regular words", () => {
    expect(fontRole(false, 55)).toBe("body");
    expect(fontRole(false, 16)).toBe("body");
  });
});
