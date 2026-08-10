# BetterIQ navigation consolidation — proposal (Aug 2026)

Follow-up to `docs/iq-module-review.md` section 9, which flagged 11 nav
destinations plus a 12th unlisted page (the cheat sheet) as more surface
than a 20-25-player club needs, with genuine overlap between some of them.

**This is a proposal for review, not an implementation.** Per the module
review's own recommendation: a navigation redesign changes muscle memory
for every existing user and this codebase's standing convention (visible
throughout its history — see any note in `CLAUDE.md` about "URLs are
unchanged") is to never break a bookmark on a reshuffle. That means this
needs a decision before code, not after.

Every claim below was checked against the actual page code (imports, API
calls, `PageIntro` copy) rather than assumed from the page names — two of
the four things flagged as "duplication" in the original audit turned out,
on a closer read, to be deliberate and already working. That distinction
matters for what should actually change.

---

## Current state

```
Overview -------------------------------------------- /admin/betteriq
Ask BetterIQ ------------------------------------ /admin/betteriq/ask
Player search ------------------------------- /admin/betteriq/player

Scout the opposition
  Match preview ------------------------------ /admin/betteriq/preview
  Opposition club ---------------------------- /admin/betteriq/opposition
  Opposition player --------------------- /admin/betteriq/opposition-player

Know your club
  Selection ----------------------------------- /admin/betteriq/selection
  Form & trends -------------------------------- /admin/betteriq/trends
  Teammates ----------------------------------- /admin/betteriq/teammates
  Team analysis ------------------------------------ /admin/betteriq/team
  Match review ------------------------------------ /admin/betteriq/review

(unlisted, reached only by a button)
  Cheat sheet --------------- /admin/betteriq/opposition/cheatsheet
```

11 nav entries + 1 hidden page, in three unlabelled/labelled groups.

---

## What's actually duplicated, and what isn't

### Not duplication — leave alone

**Match preview vs Opposition club.** The original audit flagged these as
overlapping (both fetch `iqOppositionReport`). On inspection, `MatchPreview`
explicitly frames itself as a summary with a link out: its own `PageIntro`
reads *"A 60-second read before the game… For the full dossier (danger men,
match-ups, game plan) open the scout"*, and three separate buttons
(`goScout`) link to Opposition club with the fixture/opponent carried
through. This is a deliberate summary→detail pair with working cross-links,
not accidental overlap. **No change proposed.**

**Opposition player vs the in-scout player search.** `OppositionPlayer`
(standalone page, searches ANY club via `AnyClubSearch`) and the `OppPlayerScout`
search embedded inside `OppositionScout` (searches within the CURRENT
dossier only) both render through the same shared component,
`OppPlayerDetail` from `OppPlayerProfile.jsx` — so there is no duplicated
*rendering* code, only two *entry points* to it. That's a much cheaper kind
of overlap than it first looked. **Minor change proposed below, not a merge.**

### Genuine overlap — worth consolidating

**Player search vs Form & trends.** Both let you pick a player and see the
same shape of detail (career trajectory, deep dive, radar) via the shared
`DeepDiveTab` component — but they are not actually the same tool:

- `PlayerHub` ("Player search") searches **any player at any club**
  (`AnyClubSearch`) and has a head-to-head **Compare** mode for two players
  from potentially different clubs.
- `PlayerTrends` ("Form & trends") is scoped to **our squad only**, and is
  where the season/grade filter, the movers/emerging board, and the squad
  picker live — the filter bar and the boards have no equivalent in Player
  search.

So this isn't one tool built twice — it's a generic "look up anyone"
utility and a "our squad's form dashboard" that happen to converge on the
same player-detail view. The genuine problem is that a user looking to
check one of our own players has two doors that look almost identical
(both show a picker, both open the same-shaped detail) and nothing tells
them which one has the filter bar and the movers board.

**Cheat sheet has no front door.** It's real, useful (the module review's
own conclusion: this is the single highest-value artifact for a small
club), and reachable only via a button on two other pages. Not a
duplication problem, an omission.

---

## Proposed changes

1. **Fold "Player search" into "Form & trends" as an explicit mode, not a
   separate nav entry.** `PlayerTrends`'s picker gains an "Any club"
   toggle that reveals `AnyClubSearch` and the Compare flow already built
   in `PlayerHub`; the default stays our-squad. This removes one nav entry
   without removing any capability — everything `PlayerHub` does becomes
   reachable from the merged page.
   - **Redirect**: `/admin/betteriq/player` → `/admin/betteriq/trends?any=1`
     (a plain client-side redirect, so an old bookmark still lands
     somewhere functional. `PlayerHub.jsx`'s code is deleted only once the
     merged page covers everything it did — Compare mode is the part that
     needs the most careful port).

2. **Give the cheat sheet a real nav entry** under "Scout the opposition",
   opening to an opponent picker (reusing `list_opponents`) rather than
   requiring a fixture already be selected elsewhere. The existing
   button-driven entry points (from Match preview and Opposition club)
   keep working unchanged — this only adds a third way in, for a captain
   who wants to jump straight to the printable sheet.

3. **Rename "Opposition club" → "Opposition scout"** and keep "Opposition
   player" separate — per the finding above, these are legitimately two
   different searches (whole-club dossier vs. any-club lookup) sharing a
   render, not one tool. No merge; a naming fix so "club" doesn't read as
   redundant next to "player" is the only proposed change.

4. **Leave Teammates, Team analysis, Match review, Selection, Overview, Ask
   as-is.** Each has a distinct `PageIntro` describing a genuinely
   different question ("who has this player played alongside", "how do
   we perform as a team", "what happened in this game", "who should play
   Saturday") — none of these were found to overlap with anything else
   during the review.

**Net effect**: 11 nav entries → 9, one of which (cheat sheet) is newly
reachable without a prior click, one deletion (`PlayerHub.jsx`, after its
Compare mode is ported), zero URL breakage for anything already bookmarked.
This is a smaller, more conservative change than the original review's
"~5 destinations" framing suggested — the closer read found less actual
duplication than the first pass assumed, which is itself the reason this
went through a design pass instead of being implemented directly from the
audit.

---

## Open questions for review before implementation

1. Does "Any club" belong as a toggle on Form & trends, or as a separate
   tab within the same page (Trajectory / Deep dive / Compare / **Any
   club**, alongside the existing three tabs already on the player detail
   view)? A toggle is fewer clicks for the common case (checking our own
   player); a tab is more discoverable for someone who's never used it.
2. Should the cheat sheet's new nav entry sit under "Scout the opposition"
   (matches its content) or get its own top-level slot (matches its
   status as the highest-value artifact per the module review)?
3. Is deleting `PlayerHub.jsx` acceptable once Compare mode is ported, or
   should the file stay (dead code, unrouted) until a full season has
   passed with no bug reports referencing it?

No code changes have been made for this proposal. Once these are settled,
implementation is: extend `PlayerTrends.jsx` with the any-club toggle and
Compare tab (porting logic from `PlayerHub.jsx`), add the redirect and the
new nav entry in `IQLayout.jsx`, rename the one nav label, then delete
`PlayerHub.jsx` per the answer to question 3.
