import {
  buildTemplateFile,
  type PostType,
  type Pictures,
  type TemplateFile,
} from "./buildFile";
import { extractFields, isError, nameFonts, type FontLookup } from "./extract";
import { TYPE_EXAMPLE, TYPE_NAMES, hasTypeField } from "./postFields";
import type { SessionCallback } from "./session";
import type { Extraction, Skipped } from "./types";

/** BetterCricket takes pictures up to this size (its media upload limit). */
export const PICTURE_LIMIT_BYTES = 5 * 1024 * 1024;

export type Picture = { dataUrl: string; bytes: number };

/** Which kind of picture is being fetched, so it can be sized to suit. */
export type PictureUse = "background" | "panel";

export type ExportDeps = {
  /** Runs a callback inside the one design session (see session.ts). */
  inPage: (callback: SessionCallback) => Promise<void>;
  /** Fetches one of the design's own pictures by Canva's id, sized for BetterCricket. */
  fetchImage: (ref: string, use: PictureUse) => Promise<Picture>;
  lookupFonts: FontLookup;
};

export type ExportOutcome = {
  file: TemplateFile;
  fieldCount: number;
  textCount: number;
  panelCount: number;
  /** Whether the design's own background picture is in the file. */
  background: boolean;
  /** How many free-standing pictures are in the file. */
  loosePictures: number;
  /** How many panels carry their own picture. */
  panelPictures: number;
  /** Pictures that could not be fetched, one line each. The file is still made. */
  pictureProblems: string[];
  /** Boxes that were left out of the file, and why. */
  skipped: Skipped[];
};

/** Something on the page has to be fixed before an export would be right. */
export class ExportBlocked extends Error {
  readonly skipped: Skipped[];
  constructor(message: string, skipped: Skipped[] = []) {
    super(message);
    this.skipped = skipped;
  }
}

const detailOf = (e: unknown): string =>
  e instanceof Error ? e.message : String(e);

/** Names a picture in a problem line: the background, or "Panel 2". */
const nameOf = (use: PictureUse, panel: number, loose = false): string =>
  use === "background"
    ? "Background"
    : loose
      ? `Picture ${panel}`
      : `Panel ${panel}`;

/**
 * Reads the page and builds the file: where each field and fixed word sits and
 * its colour and font roles, the panels behind the words, and the design's own
 * pictures (its background and any picture a panel is filled with). Nothing on
 * the page is touched. A picture that cannot be fetched is reported and the
 * file is still made, because the layout is worth having without it.
 */
export async function exportTemplate(
  deps: ExportDeps,
  opts: { name: string; postType: PostType },
): Promise<ExportOutcome> {
  let read: Extraction | undefined;
  await deps.inPage(async (session) => {
    const page = session.page;
    if (page.type !== "absolute") {
      throw new ExportBlocked(
        "This kind of page cannot be exported by apps. Use a normal design page.",
      );
    }
    const r = extractFields(page);
    if (isError(r)) {
      throw new ExportBlocked(r.error);
    }
    read = r;
  });
  if (!read || read.fields.length === 0) {
    throw new ExportBlocked(
      "There are no fields on this page, so there is nothing to export yet.",
      read?.skipped ?? [],
    );
  }
  if (
    !hasTypeField(
      opts.postType,
      read.fields.map((f) => f.binding),
    )
  ) {
    throw new ExportBlocked(
      opts.postType === "lineup"
        ? "A line up needs at least one player place. Add one with “Add line up”, or type {{player 1}} into a text box."
        : `A ${TYPE_NAMES[opts.postType]} post needs at least one of its own fields, such as {{${TYPE_EXAMPLE[opts.postType]}}}. Add one with the buttons for this kind of post, or type it into a text box.`,
      read.skipped,
    );
  }
  const named = await nameFonts(read, deps.lookupFonts);

  // The design's own pictures. Each is fetched once, even if two things share it.
  const pictureProblems: string[] = [];
  const byRef = new Map<string, string>();
  const want: {
    ref: string;
    use: PictureUse;
    panel: number;
    loose?: boolean;
  }[] = [];
  if (named.backgroundRef) {
    want.push({ ref: named.backgroundRef, use: "background", panel: 0 });
  }
  named.panels.forEach((p, i) => {
    if (p.imageRef && p.box && !want.some((w) => w.ref === p.imageRef)) {
      want.push({ ref: p.imageRef, use: "panel", panel: i + 1 });
    }
  });
  named.pictures.forEach((p, i) => {
    if (!want.some((w) => w.ref === p.imageRef)) {
      want.push({ ref: p.imageRef, use: "panel", panel: i + 1, loose: true });
    }
  });
  for (const w of want) {
    try {
      const pic = await deps.fetchImage(w.ref, w.use);
      if (pic.bytes > PICTURE_LIMIT_BYTES) {
        pictureProblems.push(
          `${nameOf(w.use, w.panel, w.loose)}: the picture is over BetterCricket's 5 MB limit.`,
        );
      } else {
        byRef.set(w.ref, pic.dataUrl);
      }
    } catch (e) {
      pictureProblems.push(
        `${nameOf(w.use, w.panel, w.loose)}: ${detailOf(e)}`,
      );
    }
  }
  const pictures: Pictures = {
    background: named.backgroundRef
      ? byRef.get(named.backgroundRef)
      : undefined,
    byRef,
  };
  const file = buildTemplateFile(named, {
    name: opts.name,
    postType: opts.postType,
    pictures,
  });
  return {
    file,
    fieldCount: named.fields.length,
    textCount: named.texts.length,
    panelCount: named.panels.length,
    background: !!pictures.background,
    loosePictures: (file.pictures ?? []).length,
    panelPictures: (file.panels ?? []).filter((p) => p.image).length,
    pictureProblems,
    skipped: named.skipped,
  };
}
