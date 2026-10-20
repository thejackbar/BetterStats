"""Which existing game a CSV sheet match is, when a day holds several grades.

THE CSV IMPORT USED TO LOOK AT A DATE AND ONE SHARED OPPOSITION WORD, AND
NOTHING ELSE. A club plays several grades against the same opposition on one
Saturday (Shoalwater Bay v Safety Bay: A, B and C grade), so all three sheet
matches fitted all three existing games and the first game found won. The B
grade card was linked (locked, import's copy preferred) to the A grade synced
game and the real B grade game stayed unlinked and counted: the match was held
twice, once under One Day and once under Two Day.

So a sheet match is now weighed against each candidate on two things the date
and the opposition cannot say, using rules that already exist rather than a
second copy of them:

  * THE CARD. `card_review.confirms_pair` is the bar Card review trusts a pair
    on (60% of the smaller card, at least two). A candidate whose card
    contradicts the sheet's is never linked.
  * THE GRADE. `grade_duplicates.classify_pair` decides whether two grade names
    are one grade (the discriminating tokens, letter, number, colour or
    announced format, must be identical; decoration may differ), and
    `grade_labels.suggest_categories` says when one is a different competition
    altogether (a junior grade against a senior one).

THE RANKS, strongest first:

    3  the card confirms the pair
    2  the grades correspond (and nothing contradicts)
    1  nothing else competes for either side: one sheet match, one game
    -  anything else: LEFT UNLINKED

A pair is only linked at rank 2 when it is the only such pair for both halves.
Two games of the same grade on one day against one opposition cannot be told
apart by anything here, and a wrong link hides a real game behind the wrong
card, which a missing link does not. An unlinked card is counted beside its
synced twin until a person confirms the pair in Card review's possible doubles
step, which is the safe way round; it is reported on the review, not hidden.

WHAT A CARD CAN CONTRADICT, AND WHAT IT CANNOT. A sheet's batters are compared
by player id, and a club that holds its history under initials (rule 36) has a
different player record from the synced one for the same person, so ids that
share nothing prove nothing there. A contradiction is therefore only read from
batters who ARE synced players (they carry a Cricket Australia or PlayHQ id):
three or more of them on the sheet, three or more batters on the game's card,
and at most one in common. Fewer than that, or a sheet of import-made players,
leaves the card silent and the grade decides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.services import grade_duplicates
from app.services.card_review import confirms_pair
from app.services.grade_labels import suggest_categories

# A grade verdict.
SAME = "same"          # the discriminating tokens agree
DIFFERENT = "different"  # both name a grade and they do not correspond
UNKNOWN = "unknown"    # one side names no grade, so the grade says nothing
CLASH = "clash"        # a different competition altogether (junior v senior)

# A card verdict.
CONFIRMED = "confirmed"
CONTRADICTED = "contradicted"
SILENT = "silent"

# Fewest batters on each card before a card may argue a pair is NOT the match.
MIN_FOR_CONTRADICTION = 3


def grade_verdict(sheet_grade: str, game_grade: str) -> str:
    """Do the sheet's grade and the game's grade name one grade?"""
    a = (sheet_grade or "").strip()
    b = (game_grade or "").strip()
    if not a or not b:
        return UNKNOWN
    if set(suggest_categories(a)).isdisjoint(suggest_categories(b)):
        return CLASH
    return SAME if grade_duplicates.classify_pair(a, b) else DIFFERENT


def card_verdict(sheet_all, sheet_known, card) -> str:
    """What the game's card says about the sheet match.

    `sheet_all` is every (player, runs) the sheet resolves to a player,
    `sheet_known` the subset whose player is a synced one (see the module
    note), `card` the game's own batting card.
    """
    if not sheet_all or not card:
        return SILENT
    if confirms_pair(set(sheet_all), set(card)):
        return CONFIRMED
    sheet_players = {p for p, _runs in sheet_known}
    card_players = {p for p, _runs in card}
    if (len(sheet_players) >= MIN_FOR_CONTRADICTION
            and len(card_players) >= MIN_FOR_CONTRADICTION
            and len(sheet_players & card_players) <= 1
            and len(set(sheet_known) & set(card)) <= 1):
        return CONTRADICTED
    return SILENT


def rank_pair(card: str, grade: str, lone: bool) -> Optional[int]:
    """How firmly a sheet match and a game are one match, or None to leave
    them unlinked. See the module note for the ranks."""
    if card == CONTRADICTED:
        return None
    if card == CONFIRMED:
        return 3
    if grade == CLASH:
        return None
    if grade == SAME:
        return 2
    return 1 if lone else None


@dataclass
class SheetCard:
    """What the import knows about one sheet match, for judging a candidate."""

    grade: str = ""
    signature: frozenset = field(default_factory=frozenset)
    known: frozenset = field(default_factory=frozenset)


class SheetJudge:
    """`match_pairing.assign`'s hook for the CSV import's second look."""

    def __init__(self, sheet: dict):
        self.sheet = sheet

    def _card(self, imp) -> SheetCard:
        return self.sheet.get(imp.id) or SheetCard()

    def admits(self, imp, syn) -> bool:
        sc = self._card(imp)
        return card_verdict(sc.signature, sc.known, syn.signature) != CONTRADICTED

    def rank(self, imp, syn, lone: bool) -> Optional[int]:
        sc = self._card(imp)
        return rank_pair(card_verdict(sc.signature, sc.known, syn.signature),
                         grade_verdict(sc.grade, syn.grade), lone)


@dataclass
class SheetGame:
    """One sheet match, as the date-and-opposition look sees it."""

    key: str
    played_at: Optional[date]
    tokens: set
    card: SheetCard = field(default_factory=SheetCard)


def match_by_date(sheets: list, index: dict, cards: dict, consumed: set):
    """The existing game each sheet match is, off its date and opposition.

    Returns (matched, undecided): `matched` maps a sheet key to the index
    entry it is (with `evidence` saying why), `undecided` lists the keys that
    shared a date and an opposition word with a game still free and could not
    be told which, which stay unlinked.

    Order independent: whether a pair is `lone` or the only one of its grade
    is read off the whole day, so the sheet's row order cannot change an
    answer. A manual candidate (the same sheet imported before) is never
    refused on its card: it was written from this very kind of sheet.
    """
    live: dict = {}
    for s in sheets:
        if s.played_at is None or not s.tokens:
            continue
        for ex in index.get(s.played_at, ()):
            if ex["id"] in consumed or not (s.tokens & ex["tokens"]):
                continue
            card = card_verdict(s.card.signature, s.card.known, cards.get(ex["id"]))
            if card == CONTRADICTED:
                if ex["source"] != "manual":
                    continue
                card = SILENT
            live.setdefault(s.key, []).append((ex, card))

    sheets_per_game: dict = {}
    for cands in live.values():
        for ex, _card in cands:
            sheets_per_game[ex["id"]] = sheets_per_game.get(ex["id"], 0) + 1

    by_key = {s.key: s for s in sheets}
    pairs: list = []
    for key, cands in live.items():
        for ex, card in cands:
            lone = len(cands) == 1 and sheets_per_game[ex["id"]] == 1
            rank = rank_pair(card, grade_verdict(by_key[key].card.grade,
                                                 ex.get("grade", "")), lone)
            if rank is not None:
                shared = len(set(by_key[key].card.signature)
                             & set(cards.get(ex["id"]) or ()))
                pairs.append((rank, shared, key, ex))

    matched: dict = {}
    taken: set = set()
    for rank in (3, 2, 1):
        here = [p for p in pairs if p[0] == rank
                and p[2] not in matched and p[3]["id"] not in taken]
        if rank == 3:
            here.sort(key=lambda p: (-p[1], p[2], p[3]["id"]))
        else:
            # Below a confirmed card the pair must be the ONLY one at this
            # rank for both halves, or nothing here can say which is which.
            per_key: dict = {}
            per_game: dict = {}
            for p in here:
                per_key[p[2]] = per_key.get(p[2], 0) + 1
                per_game[p[3]["id"]] = per_game.get(p[3]["id"], 0) + 1
            here = [p for p in here
                    if per_key[p[2]] == 1 and per_game[p[3]["id"]] == 1]
        for rank_, _shared, key, ex in here:
            if key in matched or ex["id"] in taken:
                continue
            matched[key] = {**ex, "evidence": {3: "card", 2: "grade", 1: "only"}[rank_]}
            taken.add(ex["id"])

    undecided = [key for key, cands in live.items()
                 if key not in matched
                 and any(ex["id"] not in taken for ex, _c in cands)]
    return matched, undecided
