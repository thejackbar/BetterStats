import type { ExportRequest, ExportResponse } from "@canva/design";
import { buildTemplateFile, type TemplateFile } from "./buildFile";
import { extractFields, isError, nameFonts, type FontLookup } from "./extract";
import { hideFields, restoreFields, type Hidden } from "./hide";
import type { SessionCallback } from "./session";
import type { Extraction, Skipped } from "./types";

/** BetterCricket takes pictures up to this size (its media upload limit). */
export const PICTURE_LIMIT_BYTES = 5 * 1024 * 1024;

export type Picture = { dataUrl: string; bytes: number };

export type ExportDeps = {
  /** Runs a callback inside the one design session (see session.ts). */
  inPage: (callback: SessionCallback) => Promise<void>;
  requestExport: (request: ExportRequest) => Promise<ExportResponse>;
  /** Downloads the exported file and returns it as a data URL. */
  fetchPicture: (url: string) => Promise<Picture>;
  lookupFonts: FontLookup;
};

export type ExportOutcome =
  | {
      status: "done";
      file: TemplateFile;
      fieldCount: number;
      textCount: number;
      panelCount: number;
      /** Size of the picture in the file, or null when the file has none. */
      pictureBytes: number | null;
      /** Boxes that were left out of the file, and why. */
      skipped: Skipped[];
    }
  | { status: "aborted" }
  | {
      status: "no_picture";
      file: TemplateFile;
      fieldCount: number;
      textCount: number;
      panelCount: number;
      pictureUrl: string | null;
      reason: string;
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

/** The placeholder words are still hidden; `hidden` is what to put back. */
export class RestoreFailed extends Error {
  readonly hidden: Hidden[];
  constructor(hidden: Hidden[], cause: unknown) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    super(
      `Your {{placeholder}} text boxes are still hidden. Press “Restore placeholders”. (${detail})`,
    );
    this.hidden = hidden;
  }
}

const detailOf = (e: unknown): string =>
  e instanceof Error ? e.message : String(e);

/** Puts hidden boxes back and saves. Throws RestoreFailed if it cannot. */
export async function restoreHidden(
  inPage: ExportDeps["inPage"],
  hidden: Hidden[],
): Promise<void> {
  if (!hidden.length) {
    return;
  }
  try {
    await inPage(async (session) => {
      if (session.page.type !== "absolute") {
        throw new Error("The page is no longer a page apps can edit.");
      }
      restoreFields(session.page, hidden);
      await session.sync();
    });
  } catch (e) {
    throw new RestoreFailed(hidden, e);
  }
}

/**
 * Makes the template file: hides the field boxes, has Canva export the page as a
 * picture, ALWAYS puts the boxes back (whether the export finished, was
 * cancelled or failed), then builds the file with the picture in it.
 *
 * `onHidden` is told what was hidden as soon as it is, so a caller can offer a
 * manual "restore" if the automatic one fails.
 */
export async function exportTemplate(
  deps: ExportDeps,
  opts: { name: string; withPicture?: boolean },
  onHidden: (hidden: Hidden[]) => void = () => {},
): Promise<ExportOutcome> {
  if (!opts.withPicture) {
    return exportStructure(deps, opts.name);
  }
  let extraction: Extraction | undefined;
  let hidden: Hidden[] = [];

  // 1. Check the page and hide the field boxes.
  try {
    await deps.inPage(async (session) => {
      const page = session.page;
      if (page.type !== "absolute") {
        throw new ExportBlocked(
          "This kind of page cannot be exported by apps. Use a normal design page.",
        );
      }
      const read = extractFields(page);
      if (isError(read)) {
        throw new ExportBlocked(read.error);
      }
      if (read.fields.length === 0) {
        throw new ExportBlocked(
          "There are no fields on this page, so there is nothing to export yet.",
        );
      }
      if (read.skipped.length) {
        throw new ExportBlocked(
          "Some text boxes would show their {{words}} in the picture. Fix them first.",
          read.skipped,
        );
      }
      hidden = hideFields(page);
      onHidden(hidden);
      extraction = read;
      await session.sync();
    });
  } catch (e) {
    // The hide may or may not have reached the design before this failed.
    if (hidden.length) {
      await restoreHidden(deps.inPage, hidden).catch(() => {
        throw new RestoreFailed(hidden, e);
      });
    }
    throw e;
  }
  if (!extraction) {
    throw new ExportBlocked("The page could not be read.");
  }
  const read = extraction;

  // 2. Export, and put the boxes back whatever happens.
  let response: ExportResponse | undefined;
  let exportError: unknown;
  try {
    response = await deps.requestExport({ acceptedFileTypes: ["png", "jpg"] });
  } catch (e) {
    exportError = e;
  }
  await restoreHidden(deps.inPage, hidden);
  if (exportError) {
    throw new Error(
      `Canva could not export the picture: ${detailOf(exportError)}`,
    );
  }
  if (!response || response.status === "aborted") {
    return { status: "aborted" };
  }

  // 3. Build the file.
  const named = await nameFonts(read, deps.lookupFonts);
  const url = response.exportBlobs[0]?.url ?? null;
  const fieldCount = named.fields.length;
  const textCount = named.texts.length;
  const panelCount = named.panels.length;
  const withoutPicture = (reason: string): ExportOutcome => ({
    status: "no_picture",
    file: buildTemplateFile(named, { name: opts.name }),
    fieldCount,
    textCount,
    panelCount,
    pictureUrl: url,
    reason,
    skipped: named.skipped,
  });
  if (!url) {
    return withoutPicture("Canva did not return a picture.");
  }
  try {
    const picture = await deps.fetchPicture(url);
    return {
      status: "done",
      file: buildTemplateFile(named, {
        name: opts.name,
        background: picture.dataUrl,
      }),
      fieldCount,
      textCount,
      panelCount,
      pictureBytes: picture.bytes,
      skipped: named.skipped,
    };
  } catch (e) {
    return withoutPicture(detailOf(e));
  }
}

/**
 * Reads the page and builds the file with no picture: where each field and fixed
 * word sits, and its colour and font roles. Nothing on the page is touched, so
 * there is nothing to hide or put back. Boxes that could not be read are listed,
 * not refused, because they cost the file nothing but themselves.
 */
async function exportStructure(
  deps: ExportDeps,
  name: string,
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
  const named = await nameFonts(read, deps.lookupFonts);
  return {
    status: "done",
    file: buildTemplateFile(named, { name }),
    fieldCount: named.fields.length,
    textCount: named.texts.length,
    panelCount: named.panels.length,
    pictureBytes: null,
    skipped: named.skipped,
  };
}
