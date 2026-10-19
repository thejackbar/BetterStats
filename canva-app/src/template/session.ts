import { openDesign } from "@canva/design";
import type { DesignEditing } from "@canva/design";

// Canva allows one design session at a time, and a session that has just ended
// can take a moment to be released. So every session here goes through one queue,
// and "a session is already open" is retried for a moment before it is reported.

let tail: Promise<unknown> = Promise.resolve();

/** Runs jobs one after another, whatever happens to the one before. */
export function exclusive<T>(job: () => Promise<T>): Promise<T> {
  const run = tail.then(job, job);
  tail = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}

const BUSY = /session is already open/i;

const wait = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

const messageOf = (e: unknown): string =>
  e instanceof Error ? e.message : String(e);

export type SessionCallback = (
  session: DesignEditing.CurrentPageSession,
) => Promise<void>;

/**
 * Opens the current page and runs the callback, one session at a time. Only an
 * "already open" refusal that happens before the callback starts is retried, so
 * the callback never runs twice.
 */
export function inCurrentPage(
  callback: SessionCallback,
  opts: { retries?: number; delayMs?: number } = {},
): Promise<void> {
  const retries = opts.retries ?? 4;
  const delayMs = opts.delayMs ?? 400;
  return exclusive(async () => {
    for (let attempt = 0; ; attempt++) {
      let started = false;
      try {
        await openDesign({ type: "current_page" }, async (session) => {
          started = true;
          await callback(session);
        });
        return;
      } catch (e) {
        if (!started && attempt < retries && BUSY.test(messageOf(e))) {
          await wait(delayMs * (attempt + 1));
          continue;
        }
        throw e;
      }
    }
  });
}
