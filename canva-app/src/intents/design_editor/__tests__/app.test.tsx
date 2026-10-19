import { useFeatureSupport } from "@canva/app-hooks";
import { findFonts } from "@canva/asset";
import { openDesign, requestExport } from "@canva/design";
import { requestOpenExternalUrl } from "@canva/platform";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { App } from "src/intents/design_editor/app";
import {
  group,
  page,
  rect,
  shape,
  textBox,
} from "src/template/__tests__/fakePage";
import { fakeSession } from "src/template/__tests__/fakeSession";
import type {
  ElementLike,
  PageLike,
  TextElementLike,
} from "src/template/types";
import { fetchPicture } from "src/template/picture";
import { copyTemplate } from "src/template/saveFile";
import { renderInTestProvider } from "src/utils/test_render";

jest.mock("@canva/app-hooks");
jest.mock("src/template/picture");
jest.mock("src/template/saveFile");

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
    // "Player 1" is also what the field picker shows, so the badge makes two.
    expect(screen.getAllByText("Player 1")).toHaveLength(2);
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

  it("lists the shapes and pictures on the page, as Canva sees them", async () => {
    showPage(
      page([
        rect({ width: 1080, height: 1080, colour: "#ffffff" }),
        shape({
          top: 120,
          left: 70,
          width: 400,
          height: 900,
          paths: [{ d: "M0 0", colour: "#7B3B3B" }],
        }),
        rect({ top: 10, left: 10, width: 200, height: 200, media: "image" }),
        textBox("{{player 1}}", { top: 200, left: 90, width: 300, height: 50 }),
      ]),
    );
    renderInTestProvider(<App />);
    check();
    await waitFor(() =>
      expect(screen.getByText("Other things on this page")).toBeTruthy(),
    );
    expect(
      screen.getByText(
        /Rectangle 1080 × 1080 at 0, 0: solid #ffffff \(the background\)$/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Shape 400 × 900 at 70, 120: solid #7b3b3b \(a panel behind your text\)$/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Rectangle 200 × 200 at 10, 10: a picture \(left out\)$/,
      ),
    ).toBeTruthy();
  });

  it("says when a shape is turned", async () => {
    showPage(
      page([
        rect({
          left: -376,
          top: 582,
          width: 1346,
          height: 451,
          rotation: 90,
          media: "image",
        }),
        textBox("{{player 1}}", {
          top: 300,
          left: 164,
          width: 700,
          height: 50,
        }),
      ]),
    );
    renderInTestProvider(<App />);
    check();
    await waitFor(() =>
      expect(
        screen.getByText(
          /Rectangle 1346 × 451 at -376, 582: a picture, turned 90° \(a panel behind your text\)$/,
        ),
      ).toBeTruthy(),
    );
  });

  it("shows no list when there is only text", async () => {
    showPage(page([textBox("{{player 1}}")]));
    renderInTestProvider(<App />);
    check();
    await waitFor(() => expect(screen.getByText(/1 field found/)).toBeTruthy());
    expect(screen.queryByText("Other things on this page")).toBeNull();
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
    // Canva's screen-reader announcer keeps the last message, so look only at the panel.
    const inPanel = screen
      .queryAllByText("Session expired")
      .filter((e) => !e.hasAttribute("data-announcer-region"));
    expect(inPanel).toHaveLength(0);
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
    // Every call to openDesign gets the same recording session, and the largest
    // number of sessions open at once is kept.
    const useSession = (o: Parameters<typeof fakeSession>[0] = {}) => {
      const fake = fakeSession(o);
      const seen = { open: 0, peak: 0 };
      jest.mocked(openDesign).mockImplementation((async (
        _options: unknown,
        callback: (session: unknown) => Promise<void>,
      ) => {
        seen.open++;
        seen.peak = Math.max(seen.peak, seen.open);
        try {
          await callback(fake.session);
        } finally {
          seen.open--;
        }
      }) as never);
      return { ...fake, seen };
    };
    const click = (name: string) =>
      fireEvent.click(screen.getByRole("button", { name }));

    it("adds a heading and 11 separate player boxes by default", async () => {
      const { calls } = useSession();
      renderInTestProvider(<App />);
      click("Add line up");
      await waitFor(() =>
        expect(screen.getByText(/12 separate text boxes/)).toBeTruthy(),
      );
      expect(calls.created).toHaveLength(12);
      expect(calls.grouped).toHaveLength(0);
      expect(calls.syncs).toBe(1);
    });

    it("groups them when the switch is on", async () => {
      const { calls } = useSession();
      renderInTestProvider(<App />);
      fireEvent.click(
        screen.getByRole("switch", { name: /Group the boxes together/ }),
      );
      click("Add line up");
      await waitFor(() =>
        expect(screen.getByText(/Line up added as one group/)).toBeTruthy(),
      );
      expect(calls.grouped).toHaveLength(1);
      expect(calls.grouped[0]).toHaveLength(12);
    });

    it("uses one session to add and re-read the page", async () => {
      const { seen } = useSession();
      renderInTestProvider(<App />);
      click("Add line up");
      await waitFor(() =>
        expect(screen.getByText(/fields? found/)).toBeTruthy(),
      );
      expect(jest.mocked(openDesign)).toHaveBeenCalledTimes(1);
      expect(seen.peak).toBe(1);
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
        expect(screen.getByText(/Match details added/)).toBeTruthy(),
      );
      expect(calls.created).toHaveLength(6);
    });

    it("adds one field at a time, each a little lower than the last", async () => {
      const { calls } = useSession();
      renderInTestProvider(<App />);
      click("Add field");
      await waitFor(() =>
        expect(screen.getByText(/Player 1 added/)).toBeTruthy(),
      );
      await waitFor(() =>
        expect(
          screen
            .getByRole("button", { name: "Add field" })
            .hasAttribute("disabled"),
        ).toBe(false),
      );
      click("Add field");
      await waitFor(() => expect(calls.created).toHaveLength(2));
      const tops = (calls.created as { top: number }[]).map((c) => c.top);
      expect(tops[1]).toBeGreaterThan(tops[0] ?? 0);
      const first = calls.created[0] as {
        text: { regions: { text: string }[] };
      };
      expect(first.text.regions[0]?.text).toBe("{{player 1}}");
    });

    it("says so, with Canva's reason, when it will not group the boxes", async () => {
      useSession({ groupFails: true });
      renderInTestProvider(<App />);
      fireEvent.click(
        screen.getByRole("switch", { name: /Group the boxes together/ }),
      );
      click("Add line up");
      await waitFor(() =>
        expect(
          screen.getByText(/would not group the boxes \(.*cannot group/),
        ).toBeTruthy(),
      );
    });

    it("names the step that failed", async () => {
      useSession({ syncFails: true });
      renderInTestProvider(<App />);
      click("Add line up");
      await waitFor(() =>
        expect(
          screen.getByText(/stopped while saving to the design/),
        ).toBeTruthy(),
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
      for (const name of ["Add line up", "Add match details", "Add field"]) {
        const b = screen.getByRole("button", { name });
        expect(
          b.hasAttribute("disabled") ||
            b.getAttribute("aria-disabled") === "true",
        ).toBe(true);
      }
    });
  });

  describe("exporting", () => {
    // A live page, so what one session changes the next one sees.
    const livePage = (elements: ElementLike[], syncFailsAt: number[] = []) => {
      const p = page(elements);
      let syncs = 0;
      const calls = { syncs: 0 };
      jest.mocked(openDesign).mockImplementation((async (
        _o: unknown,
        cb: (session: unknown) => Promise<void>,
      ) => {
        await cb({
          page: p,
          helpers: {},
          sync: async () => {
            syncs++;
            calls.syncs = syncs;
            if (syncFailsAt.includes(syncs)) {
              throw new Error("[internal_error]: sync failed");
            }
          },
        });
      }) as never);
      return calls;
    };
    const els = () => [
      textBox("LINE UP"),
      textBox("{{player 1}}", { top: 300, left: 90, transparency: 0 }),
      textBox("{{opponent}}", { top: 100, left: 90, transparency: 0.25 }),
    ];
    const back = (list: ElementLike[]) =>
      list.map((e) => (e as TextElementLike).transparency);
    const pictureOn = () =>
      fireEvent.click(
        screen.getByRole("switch", { name: /Also include my Canva picture/ }),
      );
    const exportButton = () =>
      screen.getByRole("button", { name: "Export for BetterCricket" });
    const url = "https://export.example/design.png";

    beforeEach(() => {
      jest.mocked(requestExport).mockResolvedValue({
        status: "completed",
        exportBlobs: [{ url }],
      });
      jest.mocked(fetchPicture).mockResolvedValue({
        dataUrl: "data:image/png;base64,AAAA",
        bytes: 2 * 1024 * 1024,
      });
      jest.mocked(copyTemplate).mockResolvedValue(true);
    });

    it("exports, hides the words while Canva makes the picture, and puts them back", async () => {
      const list = els();
      livePage(list);
      let hiddenAtExport: number[] = [];
      jest.mocked(requestExport).mockImplementation((async () => {
        hiddenAtExport = back(list);
        return { status: "completed", exportBlobs: [{ url }] };
      }) as never);
      renderInTestProvider(<App />);
      pictureOn();
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(
          screen.getByText(
            /Template ready: 2 fields and the picture \(2.0 MB\)/,
          ),
        ).toBeTruthy(),
      );
      expect(hiddenAtExport).toEqual([0, 1, 1]);
      expect(back(list)).toEqual([0, 0, 0.25]);
      expect(requestExport).toHaveBeenCalledWith({
        acceptedFileTypes: ["png", "jpg"],
      });
    });

    it("uses the name typed in the box", async () => {
      livePage(els());
      renderInTestProvider(<App />);
      const input = screen.getByLabelText(/Template name/);
      fireEvent.change(input, { target: { value: "Saturday XI" } });
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/Template ready/)).toBeTruthy(),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Copy template text" }),
      );
      await waitFor(() => expect(copyTemplate).toHaveBeenCalled());
      expect(copyTemplate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Saturday XI",
          format: "bettercricket-template",
        }),
      );
    });

    it("copies the template text, and says where to paste it in BetterCricket", async () => {
      livePage(els());
      renderInTestProvider(<App />);
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/Template ready/)).toBeTruthy(),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Copy template text" }),
      );
      await waitFor(() =>
        expect(
          screen.getByText(
            /Template text copied\. In BetterCricket, open BetterPosts/,
          ),
        ).toBeTruthy(),
      );
      expect(screen.getByText(/Or paste the template text/)).toBeTruthy();
      // The default file is the layout alone: no picture, and roles for the look.
      expect(copyTemplate).toHaveBeenCalledWith(
        expect.objectContaining({
          fields: expect.arrayContaining([
            expect.objectContaining({ token: "player 1", colorRole: "ink" }),
          ]),
        }),
      );
      expect(copyTemplate).toHaveBeenCalledWith(
        expect.not.objectContaining({ background: expect.anything() }),
      );
    });

    it("includes the picture only when asked", async () => {
      livePage(els());
      renderInTestProvider(<App />);
      pictureOn();
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/and the picture/)).toBeTruthy(),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Copy template text" }),
      );
      await waitFor(() => expect(copyTemplate).toHaveBeenCalled());
      expect(copyTemplate).toHaveBeenCalledWith(
        expect.objectContaining({ background: "data:image/png;base64,AAAA" }),
      );
    });

    it("does not use Canva's export at all by default", async () => {
      livePage(els());
      renderInTestProvider(<App />);
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(
          screen.getByText(/Template ready: 2 fields and 1 fixed word/),
        ).toBeTruthy(),
      );
      expect(requestExport).not.toHaveBeenCalled();
      expect(fetchPicture).not.toHaveBeenCalled();
    });

    it("carries a panel behind the text, and says so", async () => {
      livePage([
        rect({ left: 60, top: 100, width: 450, height: 900, media: "image" }),
        textBox("LINE UP", { top: 150, left: 100, width: 300, height: 50 }),
        textBox("{{player 1}}", {
          top: 250,
          left: 100,
          width: 300,
          height: 50,
        }),
      ]);
      renderInTestProvider(<App />);
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(
          screen.getByText(
            /Template ready: 1 field, 1 fixed word, and 1 panel\./,
          ),
        ).toBeTruthy(),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Copy template text" }),
      );
      await waitFor(() => expect(copyTemplate).toHaveBeenCalled());
      expect(copyTemplate).toHaveBeenCalledWith(
        expect.objectContaining({
          panels: [{ x: 60, y: 100, w: 450, h: 900, source: "picture" }],
        }),
      );
    });

    it("offers no download, because Canva's panel cannot save files", async () => {
      livePage(els());
      renderInTestProvider(<App />);
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/Template ready/)).toBeTruthy(),
      );
      expect(screen.queryByRole("button", { name: /Download/ })).toBeNull();
    });

    it("lists a box that was left out of the file", async () => {
      livePage([textBox("{{player 1}}"), textBox("vs {{opponent}}")]);
      renderInTestProvider(<App />);
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/Template ready/)).toBeTruthy(),
      );
      expect(screen.getByText(/has other words with the token/)).toBeTruthy();
    });

    it("says so when the browser refuses the copy", async () => {
      jest.mocked(copyTemplate).mockResolvedValue(false);
      livePage(els());
      renderInTestProvider(<App />);
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/Template ready/)).toBeTruthy(),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Copy template text" }),
      );
      await waitFor(() =>
        expect(screen.getByText(/would not allow copying/)).toBeTruthy(),
      );
    });

    it("warns when the picture is over BetterCricket's limit", async () => {
      jest.mocked(fetchPicture).mockResolvedValue({
        dataUrl: "data:image/png;base64,AAAA",
        bytes: 6 * 1024 * 1024,
      });
      livePage(els());
      renderInTestProvider(<App />);
      pictureOn();
      fireEvent.click(exportButton());
      await waitFor(() => expect(screen.getByText(/up to 5 MB/)).toBeTruthy());
    });

    it("leaves the design as it was when the export is cancelled", async () => {
      const list = els();
      livePage(list);
      jest.mocked(requestExport).mockResolvedValue({ status: "aborted" });
      renderInTestProvider(<App />);
      pictureOn();
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/Export cancelled/)).toBeTruthy(),
      );
      expect(back(list)).toEqual([0, 0, 0.25]);
      expect(fetchPicture).not.toHaveBeenCalled();
    });

    it("refuses, and touches nothing, while a box would show its words", async () => {
      const list = [textBox("{{player 1}}"), textBox("vs {{opponent}}")];
      livePage(list);
      renderInTestProvider(<App />);
      pictureOn();
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(
          screen.getByText(/would show their {{words}} in the picture/),
        ).toBeTruthy(),
      );
      expect(screen.getByText(/has other words with the token/)).toBeTruthy();
      expect(requestExport).not.toHaveBeenCalled();
      expect(back(list)).toEqual([0, 0]);
    });

    it("explains a page with no fields", async () => {
      livePage([textBox("LINE UP")]);
      renderInTestProvider(<App />);
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/nothing to export yet/)).toBeTruthy(),
      );
    });

    it("still gives the fields when the picture cannot be fetched", async () => {
      jest
        .mocked(fetchPicture)
        .mockRejectedValue(new Error("blocked by the security policy"));
      const list = els();
      livePage(list);
      renderInTestProvider(<App />);
      pictureOn();
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(screen.getByText(/picture could not be fetched/)).toBeTruthy(),
      );
      expect(screen.getByText(/blocked by the security policy/)).toBeTruthy();
      expect(back(list)).toEqual([0, 0, 0.25]);
      fireEvent.click(screen.getByRole("button", { name: "Open the picture" }));
      expect(requestOpenExternalUrl).toHaveBeenCalledWith({ url });
      fireEvent.click(screen.getByRole("button", { name: "Copy fields only" }));
      await waitFor(() => expect(copyTemplate).toHaveBeenCalled());
      expect(copyTemplate).toHaveBeenCalledWith(
        expect.not.objectContaining({ background: expect.anything() }),
      );
      expect(screen.queryByRole("button", { name: /Download/ })).toBeNull();
    });

    it("offers a manual restore when the words cannot be put back, and it works", async () => {
      const list = els();
      // the second save (the automatic restore) fails; the manual one is the third
      livePage(list, [2]);
      renderInTestProvider(<App />);
      pictureOn();
      fireEvent.click(exportButton());
      await waitFor(() =>
        expect(
          screen.getByText(/still hidden\. Press “Restore placeholders”/),
        ).toBeTruthy(),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Restore placeholders" }),
      );
      await waitFor(() =>
        expect(screen.getByText(/Your text boxes are back/)).toBeTruthy(),
      );
      expect(
        screen.queryByRole("button", { name: "Restore placeholders" }),
      ).toBeNull();
      expect(back(list)).toEqual([0, 0, 0.25]);
    });

    it("does not offer to export where the design cannot be edited", () => {
      jest.mocked(useFeatureSupport).mockReturnValue(() => false);
      renderInTestProvider(<App />);
      const b = exportButton();
      expect(
        b.hasAttribute("disabled") ||
          b.getAttribute("aria-disabled") === "true",
      ).toBe(true);
    });
  });
});
