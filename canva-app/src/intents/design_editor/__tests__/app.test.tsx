import { useFeatureSupport } from "@canva/app-hooks";
import { findFonts } from "@canva/asset";
import { openDesign } from "@canva/design";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { App } from "src/intents/design_editor/app";
import { group, page, textBox } from "src/template/__tests__/fakePage";
import { fakeSession } from "src/template/__tests__/fakeSession";
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
        group([textBox("{{venue}}")], { rotation: 40 }),
      ]),
    );
    renderInTestProvider(<App />);
    check();
    await waitFor(() =>
      expect(screen.getByText(/has other words with the token/)).toBeTruthy(),
    );
    expect(screen.getByText(/is locked\. Unlock it/)).toBeTruthy();
    expect(screen.getByText(/is in a rotated group/)).toBeTruthy();
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

  describe("adding blocks", () => {
    // Every call to openDesign gets the same recording session.
    const useSession = (o: Parameters<typeof fakeSession>[0] = {}) => {
      const fake = fakeSession(o);
      jest.mocked(openDesign).mockImplementation((async (
        _options: unknown,
        callback: (session: unknown) => Promise<void>,
      ) => {
        await callback(fake.session);
      }) as never);
      return fake;
    };
    const click = (name: string) =>
      fireEvent.click(screen.getByRole("button", { name }));

    it("adds a heading and 11 player boxes by default, grouped", async () => {
      const { calls } = useSession();
      renderInTestProvider(<App />);
      click("Add line up");
      await waitFor(() =>
        expect(
          screen.getByText(/Line up added to the page as one group/),
        ).toBeTruthy(),
      );
      expect(calls.created).toHaveLength(12);
      expect(calls.grouped).toHaveLength(1);
      expect(calls.syncs).toBe(1);
    });

    it("re-reads the page afterwards so the list is current", async () => {
      useSession();
      renderInTestProvider(<App />);
      click("Add line up");
      await waitFor(() =>
        expect(screen.getByText(/fields? found/)).toBeTruthy(),
      );
      // one call to add, one to check
      expect(jest.mocked(openDesign)).toHaveBeenCalledTimes(2);
    });

    it("adds as many players as the box says", async () => {
      const { calls } = useSession();
      renderInTestProvider(<App />);
      const input = screen.getByLabelText(/Players in the line up/);
      fireEvent.change(input, { target: { value: "5" } });
      fireEvent.blur(input);
      click("Add line up");
      await waitFor(() => expect(calls.created.length).toBeGreaterThan(0));
      expect(calls.created).toHaveLength(6);
    });

    it("adds the match details", async () => {
      const { calls } = useSession();
      renderInTestProvider(<App />);
      click("Add match details");
      await waitFor(() =>
        expect(
          screen.getByText(/Match details added to the page/),
        ).toBeTruthy(),
      );
      expect(calls.created).toHaveLength(6);
    });

    it("says so, and keeps the boxes, when Canva will not group them", async () => {
      useSession({ groupFails: true });
      renderInTestProvider(<App />);
      click("Add line up");
      await waitFor(() =>
        expect(screen.getByText(/would not group the boxes/)).toBeTruthy(),
      );
    });

    it("explains a locked page and adds nothing", async () => {
      const { calls } = useSession({ locked: true });
      renderInTestProvider(<App />);
      click("Add line up");
      await waitFor(() =>
        expect(screen.getByText(/page is locked/)).toBeTruthy(),
      );
      expect(calls.created).toHaveLength(0);
      expect(calls.syncs).toBe(0);
    });

    it("explains a page with no size and adds nothing", async () => {
      const { calls } = useSession({ dimensions: undefined });
      renderInTestProvider(<App />);
      click("Add line up");
      await waitFor(() =>
        expect(screen.getByText(/has no fixed size/)).toBeTruthy(),
      );
      expect(calls.created).toHaveLength(0);
    });

    it("does not offer to add where the design cannot be edited", () => {
      jest.mocked(useFeatureSupport).mockReturnValue(() => false);
      renderInTestProvider(<App />);
      for (const name of ["Add line up", "Add match details"]) {
        const b = screen.getByRole("button", { name });
        expect(
          b.hasAttribute("disabled") ||
            b.getAttribute("aria-disabled") === "true",
        ).toBe(true);
      }
    });
  });
});
