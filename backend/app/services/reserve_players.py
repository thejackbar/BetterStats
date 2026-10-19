"""Who was only a 12th man or substitute fielder: read from the SHAPE of CA's scorecard.

Cricket Australia's scorecard has no substitute marker. A team-sheet player is
`participantId`, `name`, `shortName`, `roles` and nothing else; `nonPlayingMembers` holds a
coach. A reserve who never took the field for a batting or bowling or catching line is on the
sheet and nowhere else. CA's own match list shows the game and CA's season total sometimes
leaves it out and sometimes counts it, so neither is a marker.

A named player is a RESERVE when all of these hold:
  1. their side has a batting card, meaning it batted
  2. they are not on that card at all, not even as "Did Not Bat"
  3. they have no bowling or fielding row anywhere in the game
  4. they sit beyond slot 11 on the team sheet

Everything else that is "named and nothing recorded" is a player who played, or a game that
was never going to be a match, and is NOT a reserve:
  ON_CARD_DNB        on the batting card as Did Not Bat: in the side, just did not bat
  SIDE_DID_NOT_BAT   the side never batted (rain, forfeit): there is no card to be missing from
  INSIDE_XI          off the card but in slots 1 to 11: CA counts these as often as not
  HAS_STATS          the card carries a line for them
  NOT_ON_SHEET       the id is not on the sheet (a stale team list, or a different participant)
  NO_CARD            CA returned nothing

Evidence for the rule (Applecross and Across The Waves, 121 flagged games, 98 player-seasons):
the whole gap to CA's total explained in 77 of them. In the four Applecross cases where CA's total
counted a flagged game, the club believes the players were injury substitutes. See
docs/dev-notes/archive/data-sources-and-sync.md ("The 12th man audit") and
docs/dev-notes/archive/stats-figures-records-and-filters.md ("A 12th man who did not play").
`app.scripts.audit_twelfth_man` re-runs the test against any club.

Pure functions: no I/O, no database.
"""
from __future__ import annotations

XI = 11  # the side is 11; a name past this slot is a reserve

TWELFTH_MAN = "TWELFTH_MAN"
CODES = (TWELFTH_MAN, "ON_CARD_DNB", "SIDE_DID_NOT_BAT", "INSIDE_XI", "HAS_STATS", "NOT_ON_SHEET", "NO_CARD")
_DNB_TEXT = {"did not bat", "dnb", "absent"}


def _lower(v) -> str:
    return str(v or "").lower()


def _judge(card: dict, team: dict, slot: int, guids: set[str]) -> str:
    """The class for one player (any id in `guids`) at 1-based `slot` of `team`'s sheet."""
    tid = team.get("id")
    side_batted = False
    on_card = None  # the player's own batting row on their side's card
    has_bowl_or_field = False
    for inn in card.get("innings") or []:
        if inn.get("battingTeamId") == tid and inn.get("batting"):
            side_batted = True
            for b in inn["batting"]:
                if _lower(b.get("participantId")) in guids:
                    on_card = b
        for row in (inn.get("bowling") or []) + (inn.get("fielding") or []):
            if _lower(row.get("participantId")) in guids:
                has_bowl_or_field = True
    if has_bowl_or_field:
        return "HAS_STATS"
    if on_card is not None:
        return "ON_CARD_DNB" if _lower(on_card.get("dismissalType")) in _DNB_TEXT else "HAS_STATS"
    if not side_batted:
        return "SIDE_DID_NOT_BAT"
    return "INSIDE_XI" if slot <= XI else TWELFTH_MAN


def classify(card: dict | None, guids: set[str]) -> dict:
    """Judge one named-only appearance from CA's scorecard.

    `guids` is every participant id the player can carry on a card (their own raw GUID plus
    any merged into them), lower-case. Returns {code, slot, sheet}: slot is 1-based, sheet is
    the size of the player's team list.
    """
    out = {"code": "NO_CARD", "slot": None, "sheet": None}
    if not card or not card.get("teams"):
        return out
    for t in card["teams"]:
        for i, p in enumerate(t.get("players") or []):
            if _lower(p.get("participantId")) in guids:
                out.update(slot=i + 1, sheet=len(t.get("players") or []))
                out["code"] = _judge(card, t, i + 1, guids)
                return out
    out["code"] = "NOT_ON_SHEET"
    return out


def reserve_flags(card: dict | None, team: dict | None) -> dict[str, dict]:
    """Every name on `team`'s sheet: {participantId (lower): {"slot": n, "is_reserve": bool}}.

    For the sync, which has the card in hand and writes one `game_appearances` row per name.
    Nothing is returned for a missing card or team, so the caller leaves `is_reserve` NULL
    ("not judged") and never guesses. A player with their own bowling or fielding row is never
    a reserve here, and the readers also let any stored row override the flag.
    """
    if not card or not team:
        return {}
    out: dict[str, dict] = {}
    for i, p in enumerate(team.get("players") or []):
        pid = _lower(p.get("participantId"))
        if not pid or pid in out:
            continue
        out[pid] = {"slot": i + 1, "is_reserve": _judge(card, team, i + 1, {pid}) == TWELFTH_MAN}
    return out


def sync_flags(card: dict | None, team: dict | None) -> dict[str, dict]:
    """`reserve_flags` for the sync: nothing unless CA calls the game COMPLETED.

    A card read mid-game has no batting yet, which reads as "the side never batted" and would
    stamp a judgement the sync never revisits (it does not rewrite an appearance it already
    holds). Returning nothing leaves `is_reserve` NULL, "not judged", for the backfill to read
    once the game is over.
    """
    if not card or (card.get("status") or "").upper() != "COMPLETED":
        return {}
    return reserve_flags(card, team)
