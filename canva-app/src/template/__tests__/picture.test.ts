import { refusal } from "../picture";

describe("refusal", () => {
  it("names the missing permission and where to add it", () => {
    const msg = refusal(
      new Error(
        "missing_scopes: Your app is missing one or more required scopes for this request: canva:asset:private:read.",
      ),
    );
    expect(msg).toMatch(/canva:asset:private:read/);
    expect(msg).toMatch(/Scopes in the Developer Portal/);
  });

  it("gives Canva's own words for anything else", () => {
    const msg = refusal(new Error("[not_found]: asset is not available"));
    expect(msg).toMatch(/not_found/);
    expect(msg).toMatch(/Canva library photo/);
  });

  it("still says something when the error has no text", () => {
    expect(refusal(undefined)).toMatch(
      /Canva would not give the app this picture/,
    );
  });
});
