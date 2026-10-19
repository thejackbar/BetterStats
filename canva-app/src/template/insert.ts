import type { DesignEditing } from "@canva/design";
import type { BlockSpec } from "./blocks";

export type InsertResult = { added: number; grouped: boolean };

/**
 * Adds a block's text boxes on top of everything already on the page, groups
 * them so the whole block moves as one, and saves it to the design. If Canva
 * refuses the grouping the boxes are still added, loose, and the result says so.
 */
export async function insertBlock(
  session: DesignEditing.CurrentPageSession,
  spec: BlockSpec,
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
  // Insert after the last element so the block lands on top, not behind a background.
  const existing = page.elements.toArray();
  let after: DesignEditing.AbsoluteElement | undefined =
    existing[existing.length - 1];
  const added: DesignEditing.TextElement[] = [];
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
  let grouped = false;
  try {
    await session.helpers.group({ elements: added });
    grouped = true;
  } catch {
    grouped = false;
  }
  await session.sync();
  return { added: added.length, grouped };
}
