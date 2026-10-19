// Which words in a Canva text box mean a live value in BetterCricket. This is a
// copy of the rules in frontend/src/social/boundResolve.js (bindFromToken); both
// sides are tested against token-cases.json so they cannot drift apart.

export const LINEUP_SLOTS = 15;

const MATCH_KEYS = ["competition", "round", "venue", "date", "time", "season"];

const normalise = (s: string): string =>
  s.toLowerCase().replace(/[{}]/g, "").replace(/\s+/g, " ").trim();

/** "player 3 last" becomes "lineup.3.last". null when the words are not a field. */
export function bindFromToken(token: string): string | null {
  const t = normalise(token);
  const m = t.match(/^player ?(\d{1,2})(?: (name|first|last|role))?$/);
  if (m) {
    const n = Number(m[1]);
    return n >= 1 && n <= LINEUP_SLOTS ? `lineup.${n}.${m[2] ?? "name"}` : null;
  }
  if (t === "captain" || t === "keeper" || t === "headline") {
    return t;
  }
  if (t === "opponent") {
    return "opponent";
  }
  if (t === "team" || t === "club") {
    return "team";
  }
  if (MATCH_KEYS.includes(t)) {
    return `match.${t}`;
  }
  return null;
}

const WORD: Record<string, string> = {
  name: "",
  first: " (first name)",
  last: " (last name)",
  role: " (role)",
};

/** A short plain label for the panel, e.g. "Player 3 (last name)". */
export function bindLabel(binding: string): string {
  const p = binding.match(/^lineup\.(\d+)\.(\w+)$/);
  if (p) {
    return `Player ${p[1]}${WORD[p[2] ?? ""] ?? ""}`;
  }
  const name = binding.startsWith("match.") ? binding.slice(6) : binding;
  return name.replace(/^./, (c) => c.toUpperCase());
}

const WHOLE = /^\s*\{\{\s*([^{}]+?)\s*\}\}\s*$/;

/** The word inside {{ }} when the whole text is exactly one token, else null. */
export function wholeToken(text: string): string | null {
  const m = text.match(WHOLE);
  return m ? (m[1] ?? null) : null;
}

/** True when the text has a {{ }} anywhere, whether or not it is the whole text. */
export const hasToken = (text: string): boolean => /\{\{[^{}]*\}\}/.test(text);

/**
 * {{PLAYER 1}} in capitals asks for capitals; {{player 1}} leaves the name as
 * it is. Canva does not expose its own "uppercase" effect, so the token carries it.
 */
export const wantsUppercase = (token: string): boolean =>
  /[A-Z]/.test(token) && token === token.toUpperCase();
