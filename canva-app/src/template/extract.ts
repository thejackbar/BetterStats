import { bindFromToken, hasToken, wantsUppercase, wholeToken } from "./tokens";
import type {
  Canvas,
  ElementLike,
  Extraction,
  Field,
  FormatLike,
  PageLike,
  Skipped,
  TextElementLike,
} from "./types";

const POST_WIDTH = 1080;
const POST_HEIGHTS = [1080, 1350, 1920]; // square, 4:5, story
const TOLERANCE = 0.01;

/** Scale the page to 1080 wide, and say whether its shape is one BetterPosts makes. */
export function fitToPost(width: number, height: number) {
  const scale = POST_WIDTH / width;
  const scaledH = height * scale;
  const match = POST_HEIGHTS.find(
    (h) => Math.abs(scaledH - h) / h <= TOLERANCE,
  );
  const canvas: Canvas = { w: POST_WIDTH, h: match ?? Math.round(scaledH) };
  return { scale, canvas, postSize: match !== undefined };
}

const ALIGN = {
  start: "left",
  center: "center",
  end: "right",
  justify: "left",
} as const;
const BOLD = ["semibold", "bold", "ultrabold", "heavy"];

/** The look of a text box, taken from its first run of text that carries formatting. */
function readLook(el: TextElementLike): FormatLike {
  const regions = el.text.readTextRegions();
  return regions.find((r) => r.formatting)?.formatting ?? {};
}

const isText = (el: ElementLike): el is TextElementLike => el.type === "text";

export type ExtractError = { error: string };

/**
 * Reads one page for text boxes that hold exactly one {{token}}. A box inside a
 * group is read too, with its group's position added back in. A box in a rotated
 * group is reported and left out, because its place cannot be worked out from
 * the group's corner alone.
 */
export function extractFields(page: PageLike): Extraction | ExtractError {
  if (!page.dimensions) {
    return {
      error:
        "This page has no fixed size (it looks like a whiteboard). Use a normal page such as an Instagram post.",
    };
  }
  const { scale, canvas, postSize } = fitToPost(
    page.dimensions.width,
    page.dimensions.height,
  );
  const fields: Field[] = [];
  const skipped: Skipped[] = [];
  const warnings: string[] = [];

  // A box inside a group is positioned relative to the group, so a group's own
  // position is added back in. `offset` is the sum of every group around the box.
  const scan = (
    elements: readonly ElementLike[],
    offset: { x: number; y: number },
    locked: boolean,
    rotated: boolean,
  ) => {
    for (const el of elements) {
      if (el.type === "group") {
        scan(
          el.contents.toArray(),
          { x: offset.x + el.left, y: offset.y + el.top },
          locked || el.locked,
          rotated || Math.abs(el.rotation) > 1,
        );
        continue;
      }
      if (!isText(el)) {
        continue;
      }
      const text = el.text.readPlaintext();
      if (!hasToken(text)) {
        continue;
      }
      const clean = text.replace(/\s+/g, " ").trim();
      const token = wholeToken(text);
      if (token == null) {
        skipped.push({ reason: "mixed", text: clean });
      } else if (rotated) {
        skipped.push({ reason: "rotated_group", text: clean });
      } else if (locked || el.locked) {
        skipped.push({ reason: "locked", text: clean });
      } else {
        const look = readLook(el);
        fields.push({
          token,
          binding: bindFromToken(token),
          x: Math.round((offset.x + el.left) * scale),
          y: Math.round((offset.y + el.top) * scale),
          w: Math.max(40, Math.round(el.width * scale)),
          fontRef: look.fontRef ?? null,
          fontFamily: null,
          fontSize: Math.max(8, Math.round((look.fontSize ?? 16) * scale)),
          bold: BOLD.includes(look.fontWeight ?? "normal"),
          color: look.color ?? null,
          align: ALIGN[look.textAlign ?? "start"],
          uppercase: wantsUppercase(token),
        });
        if (Math.abs(el.rotation) > 1) {
          warnings.push(
            `{{${token}}} is rotated in Canva. BetterCricket places it unrotated.`,
          );
        }
      }
    }
  };
  scan(page.elements.toArray(), { x: 0, y: 0 }, false, false);

  if (!postSize) {
    warnings.push(
      `This page is ${Math.round(page.dimensions.width)} x ${Math.round(page.dimensions.height)}, which is not a BetterCricket post shape (square, 4:5 or story). It will be cropped to fit.`,
    );
  }
  return { canvas, postSize, scale, fields, skipped, warnings };
}

export const isError = (r: Extraction | ExtractError): r is ExtractError =>
  "error" in r;

export type FontLookup = (
  refs: string[],
) => Promise<readonly { ref: string; name: string }[]>;

/** Names the fonts. A font that cannot be named is reported, never guessed. */
export async function nameFonts(
  extraction: Extraction,
  lookup: FontLookup,
): Promise<Extraction> {
  const refs = [
    ...new Set(
      extraction.fields.flatMap((f) => (f.fontRef ? [f.fontRef] : [])),
    ),
  ];
  let found: readonly { ref: string; name: string }[] = [];
  if (refs.length) {
    try {
      found = await lookup(refs);
    } catch {
      found = [];
    }
  }
  const byRef = new Map(found.map((f) => [f.ref, f.name]));
  const warnings = [...extraction.warnings];
  const fields = extraction.fields.map((f) => {
    const fontFamily = f.fontRef ? (byRef.get(f.fontRef) ?? null) : null;
    if (f.fontRef && !fontFamily) {
      warnings.push(
        `Canva would not name the font on {{${f.token}}}, so BetterCricket will use Inter for it.`,
      );
    }
    return { ...f, fontFamily };
  });
  return { ...extraction, fields, warnings };
}
