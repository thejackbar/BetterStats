import { describeSurfaces, type Surface } from "./describe";
import { findPanels, wordsPoint } from "./panels";
import { colorRole, fontRole } from "./roles";
import { bindFromToken, isAreaBinding, wantsUppercase } from "./tokens";
import { countGroups, textBoxes, type TextBox } from "./walk";
import type {
  Canvas,
  Extraction,
  Field,
  FixedText,
  FormatLike,
  PicturePlacement,
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

const MAX_FIXED = 40;
const MAX_PICTURES = 4;

/** What a box looks like, in BetterPosts' 1080 wide space, with its roles. */
function boxLook(box: TextBox, scale: number) {
  const { el } = box;
  const look = readLook(el);
  const fontSize = Math.max(8, Math.round((look.fontSize ?? 16) * scale));
  const bold = BOLD.includes(look.fontWeight ?? "normal");
  const color = look.color ?? null;
  return {
    x: Math.round((box.offset.x + el.left) * scale),
    y: Math.round((box.offset.y + el.top) * scale),
    w: Math.max(40, Math.round(el.width * scale)),
    fontRef: look.fontRef ?? null,
    fontFamily: null,
    fontSize,
    bold,
    color,
    colorRole: colorRole(color),
    fontRole: fontRole(bold, fontSize),
    align: ALIGN[look.textAlign ?? "start"],
  };
}

/**
 * A photo or sponsors field marks an AREA. The area is the smallest rectangle or
 * shape the field's word sits on, which is then not drawn as a panel; with nothing
 * under it, the text box's width and a shape that suits (a square photo, a wide strip).
 */
function takeArea(
  f: Field,
  box: TextBox,
  surfaces: Surface[],
  scale: number,
): void {
  const { el } = box;
  const p = wordsPoint({
    x: box.offset.x + el.left,
    y: box.offset.y + el.top,
    w: el.width,
    h: el.height,
    align: ALIGN[readLook(el).textAlign ?? "start"],
  });
  let best = -1;
  surfaces.forEach((sf, i) => {
    const v = sf.visual;
    const inside =
      p.x >= v.x && p.x <= v.x + v.w && p.y >= v.y && p.y <= v.y + v.h;
    const usable =
      !sf.fullPage &&
      !sf.inRotatedGroup &&
      sf.kind !== "other" &&
      sf.fill.kind !== "video";
    const current = surfaces[best];
    if (
      inside &&
      usable &&
      (!current || v.w * v.h < current.visual.w * current.visual.h)
    ) {
      best = i;
    }
  });
  const under = surfaces[best];
  if (under) {
    const x0 = Math.round(under.visual.x * scale);
    const y0 = Math.round(under.visual.y * scale);
    f.x = x0;
    f.y = y0;
    f.w = Math.max(
      40,
      Math.round((under.visual.x + under.visual.w) * scale) - x0,
    );
    f.h = Math.max(
      40,
      Math.round((under.visual.y + under.visual.h) * scale) - y0,
    );
    surfaces[best] = { ...under, use: "area" };
  } else {
    f.h = Math.round(f.binding === "sponsors" ? f.w * 0.2 : f.w);
  }
}

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
  const fieldBoxes: TextBox[] = [];
  const skipped: Skipped[] = [];
  const warnings: string[] = [];

  const texts: FixedText[] = [];
  for (const box of textBoxes(page.elements.toArray())) {
    const { el, token } = box;
    const clean = box.text.replace(/\s+/g, " ").trim();
    if (!box.hasToken) {
      // Plain words stay as written, unless they sit in a rotated group.
      if (clean && !box.rotated && texts.length < MAX_FIXED) {
        texts.push({
          text: box.text.trim(),
          ...boxLook(box, scale),
          uppercase: wantsUppercase(clean),
        });
      }
    } else if (token == null) {
      skipped.push({ reason: "mixed", text: clean });
    } else if (box.rotated) {
      skipped.push({ reason: "rotated_group", text: clean });
    } else {
      fields.push({
        token,
        binding: bindFromToken(token),
        ...boxLook(box, scale),
        h: null,
        uppercase: wantsUppercase(token),
      });
      fieldBoxes.push(box);
      if (Math.abs(el.rotation) > 1) {
        warnings.push(
          `{{${token}}} is rotated in Canva. BetterCricket places it unrotated.`,
        );
      }
    }
  }

  if (!postSize) {
    warnings.push(
      `This page is ${Math.round(page.dimensions.width)} x ${Math.round(page.dimensions.height)}, which is not a BetterCricket post shape (square, 4:5 or story). It will be cropped to fit.`,
    );
  }
  // Anything behind text becomes a panel; the rest is the background or left out.
  const anchors = textBoxes(page.elements.toArray())
    .filter((b) => b.text.trim())
    .map((b) => ({
      x: b.offset.x + b.el.left,
      y: b.offset.y + b.el.top,
      w: b.el.width,
      h: b.el.height,
      align: ALIGN[readLook(b.el).textAlign ?? "start"],
    }));
  const surfaces = describeSurfaces(page);
  fields.forEach((f, i) => {
    const box = fieldBoxes[i];
    if (box && isAreaBinding(f.binding)) {
      takeArea(f, box, surfaces, scale);
    }
  });
  const found = findPanels(surfaces, anchors, page.dimensions, scale);
  // A picture with no words on it (a cut-out player, a logo) stays a picture, under the words.
  const pictures: PicturePlacement[] = [];
  found.surfaces.forEach((sf, i) => {
    if (
      sf.use === "left_out" &&
      sf.fill.kind === "image" &&
      sf.fill.imageRef &&
      !sf.fullPage &&
      !sf.inRotatedGroup &&
      sf.kind !== "other" &&
      pictures.length < MAX_PICTURES
    ) {
      pictures.push({
        imageRef: sf.fill.imageRef,
        box: {
          x: Math.round(sf.x * scale),
          y: Math.round(sf.y * scale),
          w: Math.round(sf.w * scale),
          h: Math.round(sf.h * scale),
          rotation: sf.rotation,
        },
      });
      found.surfaces[i] = { ...sf, use: "picture" };
    }
  });
  // A picture that covers the whole page is the design's own background.
  const cover = found.surfaces.find(
    (sf) => sf.use === "background" && sf.fill.kind === "image",
  );
  return {
    canvas,
    postSize,
    scale,
    fields,
    texts,
    panels: found.panels,
    pictures,
    counts: {
      text: textBoxes(page.elements.toArray()).length,
      rects: found.surfaces.filter((sf) => sf.kind === "rect").length,
      shapes: found.surfaces.filter((sf) => sf.kind === "shape").length,
      groups: countGroups(page.elements.toArray()),
      other: found.surfaces.filter((sf) => sf.kind === "other").length,
    },
    backgroundRef:
      cover && cover.fill.kind === "image" ? cover.fill.imageRef : null,
    surfaces: found.surfaces,
    skipped,
    warnings,
  };
}

export const isError = (r: Extraction | ExtractError): r is ExtractError =>
  "error" in r;

export type FontLookup = (
  refs: string[],
) => Promise<readonly { ref: string; name: string }[]>;

/**
 * Names the fonts, for a club that wants to keep the designer's fonts. By default
 * BetterCricket uses the club's own, so a font Canva will not name is left empty
 * and BetterCricket falls back to its own, without making a fuss.
 */
export async function nameFonts(
  extraction: Extraction,
  lookup: FontLookup,
): Promise<Extraction> {
  const refs = [
    ...new Set(
      [...extraction.fields, ...extraction.texts].flatMap((f) =>
        f.fontRef ? [f.fontRef] : [],
      ),
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
  const named = <T extends { fontRef: string | null }>(f: T): T => ({
    ...f,
    fontFamily: f.fontRef ? (byRef.get(f.fontRef) ?? null) : null,
  });
  return {
    ...extraction,
    fields: extraction.fields.map(named),
    texts: extraction.texts.map(named),
  };
}
