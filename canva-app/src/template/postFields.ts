// The words a design can use on every post type other than the line up. This is a copy of
// frontend/src/social/postFields.js; both are tested against token-cases.json so they
// cannot drift apart.

export type PostType =
  | "lineup"
  | "fixtures"
  | "results"
  | "result"
  | "motm"
  | "totw"
  | "milestones"
  | "announcement"
  | "toss"
  | "events"
  | "general";

type ListDef = {
  group: string;
  max: number;
  fallback: string;
  fields: Record<string, string>;
};

const LISTS: Record<string, ListDef> = {
  fixture: {
    group: "fixture",
    max: 8,
    fallback: "opponent",
    fields: {
      opponent: "opponent",
      opp: "opponent",
      grade: "grade",
      team: "grade",
      short: "short",
      monogram: "short",
      "home away": "homeaway",
      homeaway: "homeaway",
      ha: "homeaway",
      time: "time",
      venue: "venue",
    },
  },
  result: {
    group: "result",
    max: 8,
    fallback: "opponent",
    fields: {
      opponent: "opponent",
      opp: "opponent",
      grade: "grade",
      team: "grade",
      short: "short",
      monogram: "short",
      us: "us",
      "our score": "us",
      score: "us",
      them: "them",
      "their score": "them",
      "opponent score": "them",
      outcome: "outcome",
      result: "outcome",
      margin: "margin",
    },
  },
  milestone: {
    group: "milestone",
    max: 8,
    fallback: "name",
    fields: {
      name: "name",
      first: "first",
      last: "last",
      photo: "photo",
      headshot: "photo",
      value: "value",
      number: "value",
      unit: "unit",
      date: "date",
    },
  },
  totw: {
    group: "totw",
    max: 15,
    fallback: "name",
    fields: {
      name: "name",
      first: "first",
      last: "last",
      photo: "photo",
      headshot: "photo",
      line: "line",
      performance: "line",
      grade: "grade",
      opponent: "opponent",
      opp: "opponent",
      points: "points",
    },
  },
  stat: {
    group: "stat",
    max: 6,
    fallback: "value",
    // eslint-disable-next-line formatjs/no-literal-string-in-object -- a field word, not a message
    fields: { label: "label", value: "value" },
  },
  "event item": {
    group: "item",
    max: 8,
    fallback: "title",
    fields: {
      title: "title",
      date: "date",
      day: "day",
      month: "month",
      time: "time",
      venue: "venue",
      price: "price",
    },
  },
};

const SINGLES: Record<string, string> = {
  "our score": "final.us",
  "opponent score": "final.them",
  "their score": "final.them",
  "our overs": "final.usOvers",
  "opponent overs": "final.themOvers",
  "their overs": "final.themOvers",
  result: "final.result",
  "final result": "final.result",
  margin: "final.margin",
  winner: "final.winner",
  grade: "final.grade",
  "potm name": "potm.name",
  "potm first": "potm.first",
  "potm last": "potm.last",
  "potm role": "potm.role",
  "potm bat": "potm.bat",
  "potm bowl": "potm.bowl",
  "potm line": "potm.line",
  "potm summary": "potm.summary",
  "potm photo": "potm.photo",
  toss: "toss.text",
  "toss text": "toss.text",
  "toss winner": "toss.winner",
  "toss decision": "toss.decision",
  "announcement headline": "announce.headline",
  "announcement subheadline": "announce.subheadline",
  "announcement kind": "announce.kind",
  "announcement name": "announce.name",
  "announcement first": "announce.first",
  "announcement last": "announce.last",
  "announcement photo": "announce.photo",
  "milestone title": "ms.title",
  "totw heading": "tw.heading",
  "event kicker": "event.kicker",
  "event title": "event.title",
  "event subtitle": "event.subtitle",
  "event date": "event.date",
  "event time": "event.time",
  "event venue": "event.venue",
  "event price": "event.price",
  "event cta": "event.cta",
  "event sponsor": "event.sponsor",
  "event photo": "event.photo",
};

const PERF_ALIAS: Record<string, string> = {
  our: "us",
  opponent: "them",
  their: "them",
  opposition: "them",
};

/** The other post types' words as a bind, or null when the words are not one of them. */
export function postBindFromToken(normalised: string): string | null {
  const t = normalised;
  const single = SINGLES[t];
  if (single) {
    return single;
  }
  for (const [word, def] of Object.entries(LISTS)) {
    if (!t.startsWith(word)) {
      continue;
    }
    const m = t.slice(word.length).match(/^ ?(\d{1,2})(?: (.+))?$/);
    if (!m) {
      continue;
    }
    const n = Number(m[1]);
    if (n < 1 || n > def.max) {
      return null;
    }
    const field = m[2] === undefined ? def.fallback : def.fields[m[2]];
    return field ? `${def.group}.${n}.${field}` : null;
  }
  const p = t.match(
    /^(our|opponent|their|opposition) (batter|bowler) ?(\d) ?(name|line)?$/,
  );
  if (p) {
    const n = Number(p[3]);
    return n >= 1 && n <= 3
      ? `perf.${PERF_ALIAS[p[1] ?? ""]}.${p[2] === "batter" ? "bat" : "bowl"}.${n}.${p[4] ?? "name"}`
      : null;
  }
  return null;
}

const FIELD_WORD: Record<string, string> = {
  opponent: "",
  grade: " (grade)",
  short: " (short name)",
  homeaway: " (home or away)",
  time: " (time)",
  venue: " (venue)",
  us: " (our score)",
  them: " (their score)",
  outcome: " (result)",
  margin: " (margin)",
  name: "",
  first: " (first name)",
  last: " (last name)",
  photo: " (photo)",
  value: "",
  unit: " (unit)",
  date: " (date)",
  line: " (performance)",
  points: " (points)",
  // eslint-disable-next-line formatjs/no-literal-string-in-object -- a field word, not a message
  label: " (label)",
  title: "",
  day: " (day)",
  month: " (month)",
  price: " (price)",
};
const GROUP_WORD: Record<string, string> = {
  fixture: "Fixture",
  result: "Result",
  milestone: "Milestone",
  totw: "Team of the week",
  stat: "Stat",
  item: "Event item",
};
const SINGLE_LABEL: Record<string, string> = {
  "final.us": "Our score",
  "final.them": "Opponent score",
  "final.usOvers": "Our overs",
  "final.themOvers": "Opponent overs",
  "final.result": "Result",
  "final.margin": "Margin",
  "final.winner": "Winner",
  "final.grade": "Grade",
  "potm.name": "Player of the match",
  "potm.first": "Player of the match (first name)",
  "potm.last": "Player of the match (last name)",
  "potm.role": "Player of the match (role)",
  "potm.bat": "Player of the match (batting)",
  "potm.bowl": "Player of the match (bowling)",
  "potm.line": "Player of the match (performance)",
  "potm.summary": "Player of the match (summary)",
  "potm.photo": "Player of the match (photo)",
  "toss.text": "Toss",
  "toss.winner": "Toss winner",
  "toss.decision": "Toss decision",
  "announce.headline": "Announcement headline",
  "announce.subheadline": "Announcement subheadline",
  "announce.kind": "Announcement kind",
  "announce.name": "Announcement player",
  "announce.first": "Announcement player (first name)",
  "announce.last": "Announcement player (last name)",
  "announce.photo": "Announcement photo",
  "ms.title": "Milestones title",
  "tw.heading": "Team of the week heading",
  "event.kicker": "Event kicker",
  "event.title": "Event title",
  "event.subtitle": "Event subtitle",
  "event.date": "Event date",
  "event.time": "Event time",
  "event.venue": "Event venue",
  "event.price": "Event price",
  "event.cta": "Event call to action",
  "event.sponsor": "Event sponsor",
  "event.photo": "Event photo",
};

/** A short plain label for a bind from these types, or "" when it is not one. */
export function postBindLabel(bind: string): string {
  const single = SINGLE_LABEL[bind];
  if (single) {
    return single;
  }
  let m = bind.match(
    /^(fixture|result|milestone|totw|stat|item)\.(\d+)\.(\w+)$/,
  );
  if (m) {
    return `${GROUP_WORD[m[1] ?? ""]} ${m[2]}${FIELD_WORD[m[3] ?? ""] ?? ` (${m[3]})`}`;
  }
  m = bind.match(/^perf\.(us|them)\.(bat|bowl)\.(\d)\.(name|line)$/);
  if (m) {
    return `${m[1] === "us" ? "Our" : "Opponent"} ${m[2] === "bat" ? "batter" : "bowler"} ${m[3]}${m[4] === "line" ? " (performance)" : ""}`;
  }
  return "";
}

/** Photos are areas of the design, not words. */
export const isPostAreaBinding = (bind: string | null): boolean =>
  /^(milestone|totw)\.\d+\.photo$/.test(bind ?? "") ||
  /^(potm|announce|event)\.photo$/.test(bind ?? "");

const TYPE_BINDS: Partial<Record<PostType, RegExp>> = {
  lineup: /^lineup\./,
  fixtures: /^fixture\./,
  results: /^result\.\d/,
  result: /^(final|potm|perf)\./,
  motm: /^(potm|stat)\./,
  totw: /^(totw|tw)\./,
  milestones: /^(milestone|ms)\./,
  announcement: /^announce\./,
  toss: /^toss\./,
  events: /^(event|item)\./,
};

/** Whether a design marked as this type holds at least one field of its own. Other types always pass. */
export const hasTypeField = (
  type: PostType,
  binds: (string | null | undefined)[],
): boolean => {
  const re = TYPE_BINDS[type];
  return !re || binds.some((b) => re.test(b ?? ""));
};

/** What each type is called in a sentence ("a final score post"). */
export const TYPE_NAMES: Record<PostType, string> = {
  lineup: "line up",
  fixtures: "fixtures",
  results: "results",
  result: "final score",
  motm: "player of the match",
  totw: "team of the week",
  milestones: "milestones",
  announcement: "announcement",
  toss: "toss",
  events: "event",
  general: "other",
};

/** One word of its own for each type, used in the "needs at least one field" sentence. */
export const TYPE_EXAMPLE: Record<PostType, string> = {
  lineup: "player 1",
  fixtures: "fixture 1 opponent",
  results: "result 1 our score",
  result: "our score",
  motm: "potm name",
  totw: "totw 1 name",
  milestones: "milestone 1 name",
  announcement: "announcement headline",
  toss: "toss",
  events: "event title",
  general: "opponent",
};
