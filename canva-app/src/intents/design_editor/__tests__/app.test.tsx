import { useFeatureSupport } from "@canva/app-hooks";
import { findFonts } from "@canva/asset";
import { openDesign } from "@canva/design";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { App } from "src/intents/design_editor/app";
import { group, page, textBox } from "src/template/__tests__/fakePage";
import type { PageLike } from "src/template/types";
import { renderInTestProvider } from "src/utils/test_render";

jest.mock("@canva/app-hooks");

// Makes the mocked openDesign hand its callback a session holding this page.
const showPage = (p: PageLike | { type: "unsupported" }) => {
  jest.mocked(openDesign).mockImplementation((async (
    _options: unknown,
    callback: (session: unknown) => Promise<void>,
  ) => {
    await callback({ page: p, helpers: {}, sync: async () => {} });
  }) as never);
};

const check = () =>
  fireEvent.click(screen.getByRole("button", { name: "Check this page" }));

describe("BetterCricket template panel", () => {
  beforeEach(() => {
    jest.resetAllMocks();
    jest.mocked(useFeatureSupport).mockReturnValue(() => true);
    jest.mocked(findFonts).mockResolvedValue({ fonts: [] });
  });

  it("lists the fields it finds, with what each one means", async () => {
    showPage(
      page([
        textBox("{{player 1}}"),
        textBox("{{opponent}}"),
        textBox("{{batsman 9}}"),
      ]),
    );
    renderInTestProvider(<App />);
    check();
    await waitFor(() => expect(screen.getByText("{{player 1}}")).toBeTruthy());
    expect(screen.getByText("{{opponent}}")).toBeTruthy();
    expect(screen.getByText("{{batsman 9}}")).toBeTruthy();
    expect(screen.getByText("Player 1")).toBeTruthy();
    expect(screen.getByText("Opponent")).toBeTruthy();
    expect(screen.getByText("Not a BetterCricket field")).toBeTruthy();
    expect(screen.getByText(/Post size 1080 × 1080/)).toBeTruthy();
    expect(screen.getByText(/3 fields found/)).toBeTruthy();
  });

  it("asks Canva to name the fonts it found", async () => {
    showPage(
      page([textBox("{{player 1}}", { format: { fontRef: "font-a" } })]),
    );
    renderInTestProvider(<App />);
    check();
    await waitFor(() => expect(findFonts).toHaveBeenCalled());
    expect(findFonts).toHaveBeenCalledWith({ fontRefs: ["font-a"] });
  });

  it("says what to do about a box it had to leave out", async () => {
    showPage(
      page([
        textBox("vs {{opponent}}"),
        textBox("{{date}}", { locked: true }),
        group(textBox("{{venue}}")),
      ]),
    );
    renderInTestProvider(<App />);
    check();
    await waitFor(() =>
      expect(screen.getByText(/has other words with the token/)).toBeTruthy(),
    );
    expect(screen.getByText(/is locked\. Unlock it/)).toBeTruthy();
    expect(screen.getByText(/is inside a group/)).toBeTruthy();
    expect(screen.getByText(/0 fields found|No fields found/)).toBeTruthy();
  });

  it("explains a page with no fields", async () => {
    showPage(page([textBox("LINEUP")]));
    renderInTestProvider(<App />);
    check();
    await waitFor(() =>
      expect(screen.getByText(/No fields on this page yet/)).toBeTruthy(),
    );
  });

  it("explains a page type apps cannot read", async () => {
    showPage({ type: "unsupported" });
    renderInTestProvider(<App />);
    check();
    await waitFor(() =>
      expect(screen.getByText(/cannot be read by apps/)).toBeTruthy(),
    );
  });

  it("shows an error when Canva fails, and can try again", async () => {
    jest.mocked(openDesign).mockRejectedValueOnce(new Error("Session expired"));
    renderInTestProvider(<App />);
    check();
    await waitFor(() =>
      expect(screen.getByText("Session expired")).toBeTruthy(),
    );
    showPage(page([textBox("{{date}}")]));
    check();
    await waitFor(() => expect(screen.getByText("Date")).toBeTruthy());
    expect(screen.queryByText("Session expired")).toBeNull();
  });

  it("disables the button where the design cannot be read", () => {
    jest.mocked(useFeatureSupport).mockReturnValue(() => false);
    renderInTestProvider(<App />);
    const button = screen.getByRole("button", { name: "Check this page" });
    expect(
      button.hasAttribute("disabled") ||
        button.getAttribute("aria-disabled") === "true",
    ).toBe(true);
  });
});
