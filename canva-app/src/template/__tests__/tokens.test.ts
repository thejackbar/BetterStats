import cases from "../token-cases.json";
import {
  bindFromToken,
  bindLabel,
  hasToken,
  wantsUppercase,
  wholeToken,
} from "../tokens";

describe("bindFromToken (shared with the BetterCricket editor)", () => {
  it.each(cases)("$token -> $binding", ({ token, binding }) => {
    expect(bindFromToken(token)).toBe(binding);
  });
});

describe("wholeToken", () => {
  it("reads a text box that holds only a token", () => {
    expect(wholeToken("{{player 1}}")).toBe("player 1");
    expect(wholeToken("  {{ Opponent }}  ")).toBe("Opponent");
  });
  it("does not read a token among other words", () => {
    expect(wholeToken("vs {{opponent}}")).toBeNull();
    expect(wholeToken("{{player 1}} {{player 2}}")).toBeNull();
    expect(wholeToken("player 1")).toBeNull();
    expect(wholeToken("{{}}")).toBeNull();
  });
});

describe("hasToken", () => {
  it("finds a token anywhere and ignores plain braces", () => {
    expect(hasToken("vs {{opponent}}")).toBe(true);
    expect(hasToken("{ not a token }")).toBe(false);
    expect(hasToken("{{")).toBe(false);
  });
});

describe("wantsUppercase", () => {
  it("is asked for by capitals in the token", () => {
    expect(wantsUppercase("PLAYER 1")).toBe(true);
    expect(wantsUppercase("player 1")).toBe(false);
    expect(wantsUppercase("Player 1")).toBe(false);
    expect(wantsUppercase("1")).toBe(false);
  });
});

describe("bindLabel", () => {
  it("reads plainly", () => {
    expect(bindLabel("lineup.3.last")).toBe("Player 3 (last name)");
    expect(bindLabel("lineup.3.name")).toBe("Player 3");
    expect(bindLabel("match.date")).toBe("Date");
    expect(bindLabel("opponent")).toBe("Opponent");
  });
});
