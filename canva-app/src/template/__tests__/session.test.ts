import { openDesign } from "@canva/design";
import { exclusive, inCurrentPage } from "../session";

const busyError = () =>
  new Error(
    "[bad_request]: Cannot open design - a session is already open and only one session can be open at a time.",
  );

beforeEach(() => {
  jest.resetAllMocks();
});

describe("exclusive", () => {
  it("never runs two jobs at once, in the order they were asked for", async () => {
    let running = 0;
    let peak = 0;
    const order: number[] = [];
    const job = (n: number, ms: number) => () =>
      (async () => {
        running++;
        peak = Math.max(peak, running);
        await new Promise((r) => setTimeout(r, ms));
        order.push(n);
        running--;
        return n;
      })();
    const results = await Promise.all([
      exclusive(job(1, 20)),
      exclusive(job(2, 1)),
      exclusive(job(3, 5)),
    ]);
    expect(results).toEqual([1, 2, 3]);
    expect(order).toEqual([1, 2, 3]);
    expect(peak).toBe(1);
  });

  it("carries on after a job fails, and still reports that failure", async () => {
    const failing = exclusive(async () => {
      throw new Error("boom");
    });
    const next = exclusive(async () => "fine");
    await expect(failing).rejects.toThrow("boom");
    await expect(next).resolves.toBe("fine");
  });
});

describe("inCurrentPage", () => {
  const session = { page: {} } as never;

  it("opens the current page and runs the callback once", async () => {
    jest.mocked(openDesign).mockImplementation((async (
      _o: unknown,
      cb: (s: unknown) => Promise<void>,
    ) => {
      await cb(session);
    }) as never);
    const cb = jest.fn(async () => {});
    await inCurrentPage(cb, { delayMs: 0 });
    expect(openDesign).toHaveBeenCalledWith(
      { type: "current_page" },
      expect.any(Function),
    );
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("tries again when Canva says a session is still open", async () => {
    let calls = 0;
    jest.mocked(openDesign).mockImplementation((async (
      _o: unknown,
      cb: (s: unknown) => Promise<void>,
    ) => {
      calls++;
      if (calls < 3) {
        throw busyError();
      }
      await cb(session);
    }) as never);
    const cb = jest.fn(async () => {});
    await inCurrentPage(cb, { delayMs: 0 });
    expect(calls).toBe(3);
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("gives up after its retries and reports Canva's message", async () => {
    jest.mocked(openDesign).mockRejectedValue(busyError());
    await expect(
      inCurrentPage(async () => {}, { retries: 2, delayMs: 0 }),
    ).rejects.toThrow(/session is already open/);
    expect(openDesign).toHaveBeenCalledTimes(3);
  });

  it("does not retry other errors", async () => {
    jest
      .mocked(openDesign)
      .mockRejectedValue(new Error("[internal_error]: nope"));
    await expect(inCurrentPage(async () => {}, { delayMs: 0 })).rejects.toThrow(
      /internal_error/,
    );
    expect(openDesign).toHaveBeenCalledTimes(1);
  });

  it("never runs the callback twice, even if its own error mentions a session", async () => {
    jest.mocked(openDesign).mockImplementation((async (
      _o: unknown,
      cb: (s: unknown) => Promise<void>,
    ) => {
      await cb(session);
    }) as never);
    const cb = jest.fn(async () => {
      throw busyError();
    });
    await expect(inCurrentPage(cb, { delayMs: 0 })).rejects.toThrow();
    expect(cb).toHaveBeenCalledTimes(1);
  });
});
