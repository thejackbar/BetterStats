// The slice of a Canva page this code reads, written as plain shapes so tests can
// hand it a fake page. The real design-editing types fit these (the adapter in
// app.tsx passes session.page straight in, and tsc checks that it does).

export type FormatLike = {
  fontSize?: number;
  textAlign?: "start" | "center" | "end" | "justify";
  color?: string;
  fontRef?: string;
  fontWeight?: string;
};

export type TextElementLike = {
  readonly type: "text";
  readonly locked: boolean;
  readonly width: number;
  readonly height: number;
  top: number;
  left: number;
  rotation: number;
  transparency: number;
  readonly text: {
    readPlaintext(): string;
    readTextRegions(): { text: string; formatting?: FormatLike }[];
  };
};

export type GroupElementLike = {
  readonly type: "group";
  readonly locked: boolean;
  top: number;
  left: number;
  rotation: number;
  readonly contents: { toArray(): readonly ElementLike[] };
};

export type OtherElementLike = {
  readonly type: "rect" | "shape" | "embed" | "unsupported";
};

export type ElementLike = TextElementLike | GroupElementLike | OtherElementLike;

export type PageLike = {
  readonly type: "absolute";
  readonly dimensions: { width: number; height: number } | undefined;
  readonly elements: { toArray(): readonly ElementLike[] };
};

export type SkipReason = "locked" | "mixed" | "rotated_group";

export type Skipped = { reason: SkipReason; text: string };

export type Field = {
  token: string;
  binding: string | null;
  x: number;
  y: number;
  w: number;
  /** Canva's id for the font; named later through findFonts. */
  fontRef: string | null;
  fontFamily: string | null;
  fontSize: number;
  bold: boolean;
  color: string | null;
  align: "left" | "center" | "right";
  uppercase: boolean;
};

export type Canvas = { w: number; h: number };

export type Extraction = {
  canvas: Canvas;
  /** The scale applied so the page is 1080 wide, as BetterPosts posts are. */
  scale: number;
  /** Whether the page's shape is one BetterPosts makes (square, 4:5, story). */
  postSize: boolean;
  fields: Field[];
  skipped: Skipped[];
  warnings: string[];
};
