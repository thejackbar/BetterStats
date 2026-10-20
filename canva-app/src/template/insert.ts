import type { DesignEditing } from "@canva/design";
import type { BlockSpec } from "./blocks";

export type InsertResult = {
  added: number;
  /** Whether the boxes ended up in one group. */
  grouped: boolean;
  /** Why Canva refused the grouping, when grouping was asked for and failed. */
  groupError?: string;
};

/** A failure that says which step it happened in, so the panel can too. */
export class InsertError extends Error {
  readonly step: string;
  constructor(step: string, cause: unknown) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    super(`Canva stopped while ${step}: ${detail}`);
    this.step = step;
  }
}

/**
 * Adds a block's text boxes on top of everything already on the page and saves
 * them to the design. With `group` they are also put in one group so the whole
 * block moves as one; if Canva refuses that, the boxes are still added, loose,
 * and the result says why.
 */
export async function insertBlock(
  session: DesignEditing.CurrentPageSession,
  spec: BlockSpec,
  opts: { group?: boolean } = {},
): Promise<InsertResult> {
  const page = session.page;
  if (page.type !== "absolute") {
    throw new Error(
      "This kind of page cannot be edited by apps. Use a normal design page.",
    );
  }
  if (page.locked) {
    throw new Error("This page is locked. Unlock it to add a block.");
  }
  const added: DesignEditing.TextElement[] = [];
  try {
    // Insert after the last element so the block lands on top, not behind a background.
    const existing = page.elements.toArray();
    let after: DesignEditing.AbsoluteElement | undefined =
      existing[existing.length - 1];
    // Marker rectangles first, so the words sit on top of them.
    for (const r of spec.rects ?? []) {
      const state = session.helpers.elementStateBuilder.createRectElement({
        top: r.top,
        left: r.left,
        width: r.width,
        height: r.height,
        transparency: r.transparency,
        fill: { colorContainer: { type: "solid", color: r.color } },
      });
      const el = page.elements.insertAfter(after, state);
      if (!el) {
        throw new Error("Canva would not add a rectangle to the page.");
      }
      after = el;
    }
    for (const box of spec.boxes) {
      const state = session.helpers.elementStateBuilder.createTextElement({
        top: box.top,
        left: box.left,
        width: box.width,
        text: {
          regions: [
            {
              text: box.text,
              formatting: {
                fontSize: box.fontSize,
                color: box.color,
                fontWeight: box.bold ? "bold" : "normal",
                textAlign: box.align,
              },
            },
          ],
        },
      });
      const el = page.elements.insertAfter(after, state);
      if (!el) {
        throw new Error("Canva would not add a text box to the page.");
      }
      after = el;
      if (el.type === "text") {
        added.push(el);
      }
    }
  } catch (e) {
    throw new InsertError("adding the boxes", e);
  }
  let grouped = false;
  let groupError: string | undefined;
  if (opts.group && added.length > 1) {
    try {
      await session.helpers.group({ elements: added });
      grouped = true;
    } catch (e) {
      groupError = e instanceof Error ? e.message : String(e);
    }
  }
  try {
    await session.sync();
  } catch (e) {
    throw new InsertError("saving to the design", e);
  }
  return {
    added: added.length,
    grouped,
    ...(groupError ? { groupError } : null),
  };
}
