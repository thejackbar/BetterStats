"""A squad covers one or more TEAMS (migration 336).

A club keeps a pool of players (a squad) and the teams that pool fills. Gisborne's
"MACs" squad is the pool for the 1st and 2nd XI, the next squad is for the 3rds,
the last for the 4ths, 5ths and 6ths; the women's squad can serve two women's
teams and juniors can be one squad per year group with several teams in it.

Words, because the code and the screens use them differently:

  * **squad**  a row in ``teams``: a named pool of players (``team_members``).
  * **team**   one grade the squad plays in: a ``team_sides`` row, called a SIDE
               here. "1st XI" in MACs plays in a grade, and so does "2nd XI".
  * **fixture** belongs to a squad (``fixtures.team_id``) and, through its grade,
               to one side of it.

A squad with no ``team_sides`` rows is the old single-grade squad: its one side is
read from ``teams.grade_id`` and nothing about it changes. That "virtual" side is
what keeps every existing club exactly as it was.

XI NUMBER (``rank``). The squad's order is the XI number of its first team and the
rest follow on: order 4 with three teams is the 4th, 5th and 6th XI. Derived on
read, so changing the order moves them all. It is what call-ups, the squad tiers
and the board's ordering compare. 0 (a squad nobody has ordered) is no rank.

Sides are matched to fixtures by grade NAME (sponsor suffix off, lowercased), never
by grade id, so the link survives the season rolling over and CA issuing new rows.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.grade_labels import grade_key

MAX_LABEL = 40


_XI_NUMBER = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+xi\b", re.I)


def xi_number(name) -> Optional[int]:
    """The XI number in a Cricket Australia team name: "Applecross 10th XI" -> 10.
    None when the name does not say one ("Applecross OD6 Black")."""
    m = _XI_NUMBER.search(str(name or ""))
    return int(m.group(1)) if m else None


def ordinal(n: int) -> str:
    """1 -> 1st, 2 -> 2nd, 11 -> 11th, 22 -> 22nd."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


_CLUB_FILLER = {"cc", "club", "cricket", "c", "sc", "the", "inc"}


def _tokens(name) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).split()


def club_tokens(club_name) -> list[str]:
    """The words of a club's name that CA puts in front of a team name:
    "Applecross CC" -> ["applecross"]."""
    return [t for t in _tokens(club_name) if t not in _CLUB_FILLER]


def team_name_key(name, club: Iterable[str] = ()) -> str:
    """A team name with the club's own name taken off the front and punctuation
    and spacing flattened: "Applecross OD6 Black 2" and "OD6 Black 2" both give
    "od6 black 2". Only a LEADING club name is dropped, so "Gisborne Women 2nd XI"
    never reads as "2nd XI"."""
    toks = _tokens(name)
    for c in club:
        if toks and toks[0] == c:
            toks = toks[1:]
    return " ".join(toks)


@dataclass
class Side:
    team_id: str
    key: str
    grade_name: str
    label: Optional[str]
    position: int
    rank: Optional[int]
    stored: bool          # a team_sides row; False for the old single-grade link

    @property
    def default_label(self) -> str:
        """"3rd XI" for a ranked squad, else the grade's own name."""
        if self.rank and 1 <= self.rank <= 12:
            return f"{ordinal(self.rank)} XI"
        return self.grade_name


@dataclass
class SquadInfo:
    id: str
    name: str
    short_name: Optional[str]
    sequence: int
    grade_id: Optional[str]
    is_active: bool
    sides: list[Side] = field(default_factory=list)

    @property
    def multi(self) -> bool:
        """More than one stored team: fixtures are told apart by their side."""
        return sum(1 for s in self.sides if s.stored) > 1

    def side_for_key(self, key: Optional[str]) -> Optional[Side]:
        if not key:
            return None
        return next((s for s in self.sides if s.key == key), None)

    @property
    def ranks(self) -> frozenset:
        got = {s.rank for s in self.sides if s.rank}
        if not got and self.sequence and self.sequence > 0:
            got = {self.sequence}
        return frozenset(got)

    @property
    def top_rank(self) -> Optional[int]:
        r = self.ranks
        return min(r) if r else None


class SquadSides:
    """Everything needed to answer "which squad, which team, what rank" for a club.
    Built once per request by :func:`load`; nothing here touches the database."""

    def __init__(self, squads: dict[str, SquadInfo], grade_key_by_id: dict[str, str],
                 grade_ids_by_key: dict[str, set], club: Iterable[str] = ()):
        self.squads = squads
        self.club = list(club)
        self.latest_grade_by_key: dict[str, str] = {}
        self.grade_key_by_id = grade_key_by_id
        self.grade_ids_by_key = grade_ids_by_key
        # One home per grade: the first squad claiming a key keeps it (the
        # database enforces uniqueness for stored sides; a legacy single-grade
        # link can overlap, and the lowest-ordered squad wins).
        self.key_owner: dict[str, str] = {}
        # The same, for sides a club set up on purpose (team_sides rows). Sync
        # puts a fixture on a squad by these alone: an old single-grade link is
        # a guess and keeps going through the team's name, as it always did.
        self.stored_owner: dict[str, str] = {}
        for sq in sorted(squads.values(), key=lambda s: (s.sequence or 9999, s.name)):
            for side in sq.sides:
                self.key_owner.setdefault(side.key, sq.id)
                if side.stored:
                    self.stored_owner.setdefault(side.key, sq.id)

    # -- lookups ----------------------------------------------------------
    def key_of_grade(self, grade_id) -> Optional[str]:
        return self.grade_key_by_id.get(str(grade_id)) if grade_id else None

    def squad_for_grade(self, grade_id) -> Optional[SquadInfo]:
        owner = self.key_owner.get(self.key_of_grade(grade_id) or "")
        return self.squads.get(owner) if owner else None

    def squad_for_stored_grade(self, grade_id) -> Optional[SquadInfo]:
        owner = self.stored_owner.get(self.key_of_grade(grade_id) or "")
        return self.squads.get(owner) if owner else None

    def squad_for_team_name(self, grade_id, team_name) -> Optional[SquadInfo]:
        """The squad a fixture belongs to by OUR team's name, for when two of the
        club's teams play in one grade and the grade cannot tell them apart.

        Only ever a correction to the grade's own squad (or a home for a grade no
        squad plays). Two things can name a squad, the name first:

          * the squad's own name or short name IS the team's name once the club's
            name is taken off the front ("Applecross OD6 Black 2" -> squad
            "OD6 Black 2"), exactly one active squad answering;
          * the name states an XI number ("Applecross 10th XI") that the grade's own
            squad does not carry and exactly one other active squad does.

        When the grade's own squad already fits the name, a name no squad carries,
        or two squads answering, the answer is None and the grade decides."""
        owner = self.squads.get(self.key_owner.get(self.key_of_grade(grade_id) or "", ""))
        key = team_name_key(team_name, self.club)
        if key:
            def named(sq: SquadInfo) -> bool:
                return key in {team_name_key(sq.name, self.club), team_name_key(sq.short_name, self.club)}
            if owner is not None and named(owner):
                return None
            hits = [s for s in self.squads.values() if s.is_active and named(s)]
            if len(hits) == 1:
                return hits[0]
        n = xi_number(team_name)
        if not n or owner is None or n in owner.ranks:
            return None
        hits = [s for s in self.squads.values() if s.is_active and n in s.ranks]
        return hits[0] if len(hits) == 1 else None

    def resolve(self, team_id, grade_id, side_key=None) -> tuple[Optional[SquadInfo], Optional[Side]]:
        """The squad and team a fixture (its ``team_id``, ``grade_id`` and
        ``side_key``) belongs to. A fixture naming a squad is that squad's; one
        that names none is found by its grade. A team the club picked on the
        fixture (``side_key``) wins over the one its grade implies, but only when
        that squad actually has it: a stale key falls back to the grade."""
        key = self.key_of_grade(grade_id)
        if side_key:
            sq0 = self.squads.get(str(team_id)) if team_id else None
            if sq0 is not None and sq0.side_for_key(side_key) is not None:
                key = side_key
        sq = self.squads.get(str(team_id)) if team_id else None
        if sq is None and key:
            sq = self.squads.get(self.key_owner.get(key, ""))
        if sq is None:
            return None, None
        return sq, sq.side_for_key(key)

    def rank(self, team_id, grade_id, side_key=None) -> Optional[int]:
        """The fixture's XI number: its team's, else the squad's own order."""
        sq, side = self.resolve(team_id, grade_id, side_key)
        if sq is None:
            return None
        if side is not None and side.rank:
            return side.rank
        return sq.sequence if sq.sequence and sq.sequence > 0 else None

    def name(self, team_id, grade_id, side_key=None) -> Optional[str]:
        """What the fixture's team is called. A squad with several teams names
        each by its label; any other squad is called by its own name, as ever."""
        sq, side = self.resolve(team_id, grade_id, side_key)
        if sq is None:
            return None
        if sq.multi and side is not None:
            return side.label or side.default_label
        if side is not None and side.stored and side.label:
            return side.label
        return sq.short_name or sq.name

    def squad_name(self, team_id, grade_id, side_key=None) -> Optional[str]:
        sq, _ = self.resolve(team_id, grade_id, side_key)
        return (sq.short_name or sq.name) if sq else None

    def squad_id(self, team_id, grade_id, side_key=None) -> Optional[str]:
        sq, _ = self.resolve(team_id, grade_id, side_key)
        return sq.id if sq else None

    def grade_ids(self, team_id) -> set:
        """Every grade row (any season) whose name is one of this squad's teams."""
        sq = self.squads.get(str(team_id))
        if sq is None:
            return set()
        out: set = set()
        for side in sq.sides:
            out |= self.grade_ids_by_key.get(side.key, set())
        if sq.grade_id:
            out.add(str(sq.grade_id))
        return out

    def same_team_grade_ids(self, team_id, grade_id, side_key=None) -> Optional[set]:
        """The grade rows that make up the SAME team as this fixture's, when the
        squad has several teams; None when the squad is one team (every fixture of
        the squad is the same side, as before)."""
        sq = self.squads.get(str(team_id)) if team_id else None
        if sq is None or not sq.multi:
            return None
        key = self.key_of_grade(grade_id)
        if side_key and sq.side_for_key(side_key) is not None:
            key = side_key
        return set(self.grade_ids_by_key.get(key, set())) if key else None

    def grade_names(self, team_id) -> list[str]:
        sq = self.squads.get(str(team_id))
        return [s.grade_name for s in sq.sides] if sq else []


async def load(db: AsyncSession, club_id) -> SquadSides:
    """Read a club's squads, their teams and the grade names fixtures are matched on."""
    team_rows = (await db.execute(
        text(
            "SELECT t.id, t.name, t.short_name, COALESCE(t.sequence, 0), t.grade_id, "
            "COALESCE(t.is_active, true), COALESCE(gr.display_name_override, gr.name) "
            "FROM teams t LEFT JOIN grades gr ON gr.id = t.grade_id "
            "WHERE t.organisation_id = :org"
        ),
        {"org": club_id},
    )).fetchall()
    grade_rows = (await db.execute(
        text(
            "SELECT gr.id, gr.name FROM grades gr JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = :org ORDER BY s.year DESC NULLS LAST, s.name DESC"
        ),
        {"org": club_id},
    )).fetchall()
    side_rows = (await db.execute(
        text(
            "SELECT team_id, grade_key, grade_name, label, position FROM team_sides "
            "WHERE organisation_id = :org ORDER BY team_id, position, grade_name"
        ),
        {"org": club_id},
    )).fetchall()

    grade_key_by_id: dict[str, str] = {}
    grade_ids_by_key: dict[str, set] = {}
    latest_by_key: dict[str, str] = {}      # newest season first, so the first seen wins
    for gid, gname in grade_rows:
        k = grade_key(gname)
        grade_key_by_id[str(gid)] = k
        grade_ids_by_key.setdefault(k, set()).add(str(gid))
        latest_by_key.setdefault(k, str(gid))

    stored: dict[str, list] = {}
    for tid, key, gname, label, pos in side_rows:
        stored.setdefault(str(tid), []).append((key, gname, label, pos))

    squads: dict[str, SquadInfo] = {}
    for tid, name, short, seq, gid, active, gname in team_rows:
        sid = str(tid)
        sq = SquadInfo(id=sid, name=name, short_name=short, sequence=int(seq or 0),
                       grade_id=str(gid) if gid else None, is_active=bool(active))
        rows = stored.get(sid)
        if rows:
            sq.sides = [
                Side(team_id=sid, key=k, grade_name=gn, label=lab, position=i,
                     rank=(sq.sequence + i) if sq.sequence > 0 else None, stored=True)
                for i, (k, gn, lab, _p) in enumerate(rows)
            ]
        elif gname:
            sq.sides = [Side(team_id=sid, key=grade_key(gname), grade_name=gname, label=None, position=0,
                             rank=sq.sequence if sq.sequence > 0 else None, stored=False)]
        squads[sid] = sq
    club_name = (await db.execute(
        text("SELECT name FROM organisations WHERE id = :org"), {"org": club_id})).scalar()
    out = SquadSides(squads, grade_key_by_id, grade_ids_by_key, club_tokens(club_name))
    out.latest_grade_by_key = latest_by_key
    return out


# ── Writing ───────────────────────────────────────────────────────────────────
@dataclass
class SideSpec:
    grade_id: str
    label: Optional[str] = None


def clean_label(value) -> Optional[str]:
    v = " ".join(str(value or "").split())[:MAX_LABEL]
    return v or None


async def replace_sides(db: AsyncSession, club_id, team, specs: list[SideSpec]) -> dict:
    """Set the squad's teams to ``specs``, in order.

    Every grade must be one of this club's. A grade belongs to one squad only, so a
    grade being taken from another squad leaves that squad (returned as
    ``moved_from`` so the screen can say so). ``team.grade_id`` follows the first
    team, which keeps the ladder and the old single-grade readers working.
    Returns ``{"moved_from": [squad names], "keys": [grade keys]}``.
    """
    ids = []
    for s in specs:
        try:
            ids.append(uuid.UUID(str(s.grade_id)))
        except (ValueError, AttributeError, TypeError):
            continue
    names: dict[str, str] = {}
    if ids:
        for gid, gname in (await db.execute(
            text("SELECT gr.id, COALESCE(gr.display_name_override, gr.name) FROM grades gr "
                 "JOIN seasons s ON s.id = gr.season_id "
                 "WHERE s.organisation_id = :org AND gr.id = ANY(CAST(:ids AS uuid[]))"),
            {"org": club_id, "ids": ids},
        )).fetchall():
            names[str(gid)] = gname

    seen: set[str] = set()
    ordered: list[tuple[str, str, str, Optional[str]]] = []   # (key, name, grade_id, label)
    for s in specs:
        gname = names.get(str(s.grade_id))
        if not gname:
            continue
        k = grade_key(gname)
        if k in seen:
            continue
        seen.add(k)
        ordered.append((k, gname, str(s.grade_id), clean_label(s.label)))

    moved: list[str] = []
    if ordered:
        taken = (await db.execute(
            text("SELECT DISTINCT t.name FROM team_sides ts JOIN teams t ON t.id = ts.team_id "
                 "WHERE ts.organisation_id = :org AND ts.team_id <> :tid AND ts.grade_key = ANY(CAST(:keys AS text[]))"),
            {"org": club_id, "tid": team.id, "keys": [o[0] for o in ordered]},
        )).fetchall()
        moved = sorted({r[0] for r in taken})
        await db.execute(
            text("DELETE FROM team_sides WHERE organisation_id = :org AND team_id <> :tid "
                 "AND grade_key = ANY(CAST(:keys AS text[]))"),
            {"org": club_id, "tid": team.id, "keys": [o[0] for o in ordered]},
        )
    await db.execute(text("DELETE FROM team_sides WHERE team_id = :tid"), {"tid": team.id})
    for pos, (k, gname, _gid, label) in enumerate(ordered):
        await db.execute(
            text("INSERT INTO team_sides (team_id, organisation_id, grade_key, grade_name, label, position) "
                 "VALUES (:tid, :org, :k, :gn, :lab, :pos)"),
            {"tid": team.id, "org": club_id, "k": k, "gn": gname, "lab": label, "pos": pos},
        )
    if ordered:
        team.grade_id = uuid.UUID(ordered[0][2])
    return {"moved_from": moved, "keys": [o[0] for o in ordered]}


async def assign_fixtures(db: AsyncSession, club_id, team_id, today: Optional[date] = None) -> int:
    """Put the squad's upcoming fixtures on the squad: every fixture in one of its
    teams' grades that CA drew (or that names no squad) now names this one.

    Hand-made fixtures that already name a squad are left alone: that choice was
    typed by somebody. Past games are history and are not touched."""
    sides = await load(db, club_id)
    gids = [uuid.UUID(g) for g in sides.grade_ids(team_id)]
    tid = uuid.UUID(str(team_id))
    rows = (await db.execute(
        text(
            "SELECT id, grade_id, home_team, away_team, home_away FROM fixtures "
            "WHERE organisation_id = :org "
            "AND played_on >= :today AND COALESCE(status, '') <> 'CANCELLED' "
            "AND team_id IS DISTINCT FROM :tid AND NOT COALESCE(team_pinned, false) "
            "AND (source = 'grassroots' OR team_id IS NULL)"
        ),
        {"tid": tid, "org": club_id, "today": today or date.today()},
    )).fetchall()
    # A fixture whose own team's name says it is another squad's (the 10th XI in a
    # grade the 8th XI also plays) stays with that squad; one whose name says it is
    # THIS squad's comes across even from a grade this squad does not play ("OD6
    # Black 2" in the grade the "OD6 Black" squad plays).
    gid_set = {str(g) for g in gids}
    mine = []
    for fid, gid, home, away, home_away in rows:
        our = home if home_away == "HOME" else away if home_away == "AWAY" else None
        named = sides.squad_for_team_name(gid, our)
        if named is not None:
            if named.id == str(tid):
                mine.append(fid)
        elif gid is not None and str(gid) in gid_set:
            mine.append(fid)
    if not mine:
        return 0
    res = await db.execute(
        text("UPDATE fixtures SET team_id = :tid, updated_at = NOW() "
             "WHERE id = ANY(CAST(:ids AS uuid[])) RETURNING id"),
        {"tid": tid, "ids": mine},
    )
    return len(res.fetchall())


def sides_payload(sq: SquadInfo) -> list[dict]:
    """A squad's teams for the screen."""
    return [
        {
            "key": s.key, "grade_name": s.grade_name, "label": s.label,
            "default_label": s.default_label, "rank": s.rank, "position": s.position,
            "stored": s.stored,
        }
        for s in sq.sides
    ]
