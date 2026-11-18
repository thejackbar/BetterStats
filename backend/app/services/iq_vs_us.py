"""BetterIQ: one opposition player's record AGAINST US, game by game.

The dossier's ``vs_us`` block only covers players in this season's squad scan
and only carries totals. A coach scouting a player wants the detail behind it:
which of our bowlers has dismissed them, which of our fielders has caught them,
and which of our batters they have dismissed. All of that is in the full
Cricket Australia scorecard of each game we played against their club, so this
reads those cards (the same games ``_our_games_vs`` lists for the dossier's
head-to-head) and keeps only the rows that involve this one player.

* Pure reads: our games list and our player ids come from the database in the
  request; the cards come from the shared scorecard cache. Nothing about the
  opponent is written anywhere except the JSON cache row (rule 13).
* Our side is the team on the card that is not theirs. A name in a
  ``dismissalText`` is resolved to a participant through that innings' bowling
  and fielding rows first, then the team sheet. Our participant GUID maps to our
  own player id (``players.grassroots_id`` scoped to our club) so names link to
  our player pages.
* Cached in ``opposition_dossiers`` under ``pvsus::`` keys, built in the
  background and polled, like the deep scan. The Grade Type / Match Type scope
  narrows which of our games count, so it is part of the cache key.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.iq_opponent import (
    _DISMISSAL_SHORT,
    _NOT_AN_INNINGS,
    _balls_to_overs,
    _find_opponent_team,
    _is_redacted_name,
    _is_uuid,
    _match_date,
    _norm,
    _our_games_vs,
    _overs_to_balls,
    _scope_labels,
    _scope_sig,
)
from app.services.iq_scout import _get_or_start
from app.services.sync import (
    _caught_by_keeper,
    _innings_keeper_names,
    _norm_name,
    _parse_bowler_and_fielder,
)

VS_US_VERSION = 1
MAX_VS_US_GAMES = 60   # our most recent games against their club that we check

# CA spells a few dismissal types two ways. The parser in sync expects the
# short spelling, so fold the long ones in before parsing.
_DT_FOR_PARSER = {
    "Leg Before Wicket": "LBW",
    "Caught & Bowled": "Caught",
    "Caught and Bowled": "Caught",
}
_BOWLER_CREDIT = {"Caught", "Bowled", "LBW", "Stumped", "Hit Wicket"}
_RUN_OUT_RE = re.compile(r"^run\s*out:?\s*\(?\s*(.+?)\s*\)?\s*$", re.IGNORECASE)


def _key(name: str | None) -> str:
    return _norm_name(name or "").replace("†", "").strip().lower()


def _cache_key(opp_key: str, player_id: str) -> str:
    key = f"pvsus::{opp_key.strip().lower()}::{player_id.strip().lower()}"
    sig = _scope_sig()
    if sig:
        key += f"::sc::{sig}"
    return key


def _team_short_names(team: dict) -> dict[str, str]:
    """normalised short name -> participantId for everyone on a team sheet."""
    out: dict[str, str] = {}
    for pl in ((team.get("players") or []) + (team.get("nonPlayingMembers") or [])):
        pid = pl.get("participantId") or pl.get("id")
        for nm in (pl.get("playerShortName"), pl.get("displayName"), pl.get("name")):
            if pid and nm:
                out.setdefault(_key(nm), pid)
    return out


def _team_pids(team: dict) -> dict[str, str]:
    """lowercased participantId -> display name."""
    out: dict[str, str] = {}
    for pl in ((team.get("players") or []) + (team.get("nonPlayingMembers") or [])):
        pid = pl.get("participantId") or pl.get("id")
        if pid:
            out[pid.lower()] = pl.get("displayName") or pl.get("name") or pl.get("playerShortName") or ""
    return out


def _find_player_in_team(team: dict, pid_l: str, player_name: str | None) -> str | None:
    """This player's participant id on the card: by GUID, else by full name when
    exactly one player on their sheet carries it (CA can issue a different GUID
    on a different route). Returns the lowercased id used on this card."""
    pids = _team_pids(team)
    if pid_l in pids:
        return pid_l
    want = _key(player_name)
    if not want or _is_redacted_name(player_name):
        return None
    hits = [p for p, nm in pids.items() if _key(nm) == want]
    return hits[0] if len(hits) == 1 else None


def _resolve(name: str | None, *maps: dict[str, str]) -> str | None:
    k = _key(name)
    if not k:
        return None
    for m in maps:
        if k in m:
            return m[k]
    return None


def _parse_dismissal(row: dict, keeper_names: set[str]) -> dict:
    """Method, bowler name and fielder name(s) from one batting row."""
    dt_long = row.get("dismissalType") or ""
    d_text = row.get("dismissalText") or ""
    method = _DISMISSAL_SHORT.get(dt_long, dt_long.lower()) if dt_long else "unknown"
    dt = _DT_FOR_PARSER.get(dt_long, dt_long)
    bowler = fielder = None
    if dt in _BOWLER_CREDIT:
        bowler, fielder, parsed = _parse_bowler_and_fielder(d_text, dt)
        if parsed == "caught and bowled":
            method, fielder = "c&b", None
    fielders: list[str] = [fielder] if fielder else []
    if method == "run out":
        m = _RUN_OUT_RE.match(_norm_name(d_text).strip())
        if m:
            fielders = [f.strip().lstrip("†").strip() for f in m.group(1).split("/") if f.strip()]
    if method == "caught" and _caught_by_keeper(d_text, keeper_names):
        method = "caught behind"
    return {"method": method, "bowler": bowler, "fielders": fielders}


async def _our_player_ids(session: AsyncSession, org_id: str) -> dict[str, dict]:
    """Our club's players keyed by raw CA GUID (lowercased) -> {id, name}.
    Scoped to our club (rule 3: player ids are per club)."""
    res = await session.execute(
        text(
            """
            SELECT p.id::text AS id, COALESCE(p.grassroots_id, p.id::text) AS guid,
                   COALESCE(NULLIF(p.display_name_override, ''), p.name) AS name
            FROM players p
            WHERE p.organisation_id = CAST(:org AS UUID)
            """
        ),
        {"org": org_id},
    )
    return {r["guid"].lower(): {"id": r["id"], "name": r["name"]} for r in res.mappings() if r["guid"]}


def _bump(acc: dict, who: dict, field: str, *, method: str | None = None, when: str | None = None,
          runs: int | None = None) -> None:
    k = who["player_id"] or f"name:{_key(who['name'])}"
    e = acc.setdefault(k, {"player_id": who["player_id"], "name": who["name"], "count": 0,
                           "methods": Counter(), "dates": [], "runs": []})
    e["count"] += 1
    e[field] = e.get(field, 0) + 1
    if method:
        e["methods"][method] += 1
    if when:
        e["dates"].append(when)
    if runs is not None:
        e["runs"].append(runs)


def _finish(acc: dict) -> list[dict]:
    out = []
    for e in acc.values():
        row = dict(e)
        row["methods"] = [{"type": t, "count": c} for t, c in e["methods"].most_common()]
        row["last_date"] = max(e["dates"]) if e["dates"] else None
        row.pop("dates", None)
        if not row["runs"]:
            row.pop("runs", None)
        out.append(row)
    out.sort(key=lambda r: (-r["count"], r["name"] or ""))
    return out


async def _build(
    our_org_id: str, our_name: str | None, opp_key: str, opp_org_id: str | None, opp_name: str | None,
    player_id: str, player_name: str | None, games: list[dict], ours: dict[str, dict],
    scope: list[str],
) -> dict:
    pid_l = player_id.strip().lower()
    checked = 0
    no_card = 0
    played: list[dict] = []
    bat_inns: list[dict] = []
    spells: list[dict] = []
    got_them_out: dict = {}      # our bowlers who dismissed them
    fielded_them: dict = {}      # our fielders who caught / stumped / ran them out
    victims: dict = {}           # our batters they dismissed (as bowler)
    their_fielding: dict = {}    # our batters they caught / stumped / ran out
    seen_name = player_name

    def our_who(pid: str | None, fallback: str | None) -> dict | None:
        """A participant on OUR side as {player_id, name}; None when it is a
        redacted name we cannot put a real name to."""
        rec = ours.get((pid or "").lower()) if pid else None
        name = (rec or {}).get("name") or fallback
        if _is_redacted_name(name):
            return None
        return {"player_id": (rec or {}).get("id"), "name": name}

    for g in games[:MAX_VS_US_GAMES]:
        sc = await gr.get_match_scorecard(g["id"])
        if not sc:
            no_card += 1
            continue
        checked += 1
        their = _find_opponent_team(sc, our_org_id=our_org_id, opp_org_id=opp_org_id, opp_name=opp_name)
        if not their:
            continue
        us = next((t for t in (sc.get("teams") or []) if t is not their and t.get("id") != their.get("id")), None)
        if not us:
            continue
        me = _find_player_in_team(their, pid_l, player_name)
        if not me:
            continue
        their_pids = _team_pids(their)
        our_pids = _team_pids(us)
        seen_name = seen_name or their_pids.get(me)
        our_names = _team_short_names(us)
        their_names = _team_short_names(their)
        when = _match_date(sc) or g.get("played_at")
        when_s = when.isoformat() if isinstance(when, date) else (str(when)[:10] if when else None)
        game = {
            "game_id": g["id"], "date": when_s, "grade": g.get("grade_name"),
            "our_team": us.get("displayName") or us.get("name"),
            "their_team": their.get("displayName") or their.get("name"),
            "bat": None, "bowl": None, "field": None,
        }

        for inn in sc.get("innings") or []:
            batting = inn.get("batting") or []
            bowling = inn.get("bowling") or []
            fielding = inn.get("fielding") or []
            keeper_names = _innings_keeper_names(fielding)
            bowl_names = {_key(r.get("playerShortName")): r.get("participantId")
                          for r in bowling if r.get("playerShortName") and r.get("participantId")}
            field_names = {_key(r.get("playerShortName")): r.get("participantId")
                           for r in fielding if r.get("playerShortName") and r.get("participantId")}
            bat_pids = {(r.get("participantId") or "").lower() for r in batting}
            their_innings = bool(bat_pids & set(their_pids))
            our_innings = not their_innings and bool(bat_pids & set(our_pids))

            if their_innings:
                for r in batting:
                    if (r.get("participantId") or "").lower() != me:
                        continue
                    dt_id = r.get("dismissalTypeId") or 0
                    if dt_id == 0 or _norm(r.get("dismissalType")) in _NOT_AN_INNINGS:
                        continue
                    not_out = dt_id == 1
                    runs = r.get("runsScored") or 0
                    balls = r.get("ballsFaced")
                    inn_row = {
                        "date": when_s, "grade": g.get("grade_name"), "runs": runs,
                        "balls": balls, "not_out": not_out, "dismissal": None,
                        "bowler": None, "fielders": [],
                    }
                    if not not_out:
                        d = _parse_dismissal(r, keeper_names)
                        inn_row["dismissal"] = d["method"]
                        if d["bowler"]:
                            bpid = _resolve(d["bowler"], bowl_names, our_names)
                            who = our_who(bpid, d["bowler"])
                            if who:
                                inn_row["bowler"] = who
                                _bump(got_them_out, who, "wickets", method=d["method"], when=when_s)
                        for fname in d["fielders"]:
                            fpid = _resolve(fname, field_names, our_names)
                            who = our_who(fpid, fname)
                            if not who:
                                continue
                            inn_row["fielders"].append(who)
                            kind = ("stumpings" if d["method"] == "stumped"
                                    else "run_outs" if d["method"] == "run out" else "catches")
                            _bump(fielded_them, who, kind, method=d["method"], when=when_s)
                    bat_inns.append(inn_row)
                    game["bat"] = inn_row

            if our_innings:
                for r in bowling:
                    if (r.get("participantId") or "").lower() != me:
                        continue
                    spell = {
                        "date": when_s, "grade": g.get("grade_name"),
                        "balls": _overs_to_balls(r.get("oversBowled")),
                        "maidens": r.get("maidensBowled") or 0,
                        "runs": r.get("runsConceded") or 0,
                        "wickets": r.get("wicketsTaken") or 0,
                        "victims": [],
                    }
                    spells.append(spell)
                    game["bowl"] = spell
                field_log = {"catches": 0, "stumpings": 0, "run_outs": 0, "victims": []}
                for r in batting:
                    dt_id = r.get("dismissalTypeId") or 0
                    if dt_id in (0, 1) or _norm(r.get("dismissalType")) in _NOT_AN_INNINGS:
                        continue
                    d = _parse_dismissal(r, keeper_names)
                    bat_pid = r.get("participantId")
                    who = our_who(bat_pid, our_pids.get((bat_pid or "").lower()) or r.get("playerShortName"))
                    runs = r.get("runsScored")
                    if d["bowler"] and (_resolve(d["bowler"], bowl_names, their_names) or "").lower() == me:
                        if who:
                            _bump(victims, who, "wickets", method=d["method"], when=when_s,
                                  runs=int(runs) if runs is not None else None)
                            if game["bowl"] is not None:
                                game["bowl"]["victims"].append(who["name"])
                    for fname in d["fielders"]:
                        if (_resolve(fname, field_names, their_names) or "").lower() != me:
                            continue
                        kind = ("stumpings" if d["method"] == "stumped"
                                else "run_outs" if d["method"] == "run out" else "catches")
                        field_log[kind] += 1
                        if who:
                            field_log["victims"].append(who["name"])
                            _bump(their_fielding, who, kind, method=d["method"], when=when_s)
                if field_log["catches"] or field_log["stumpings"] or field_log["run_outs"]:
                    game["field"] = field_log
        played.append(game)

    return _assemble(
        our_name=our_name, opp_key=opp_key, opp_name=opp_name, player_id=player_id,
        player_name=seen_name, games_total=len(games), checked=checked, no_card=no_card,
        played=played, bat_inns=bat_inns, spells=spells, got_them_out=got_them_out,
        fielded_them=fielded_them, victims=victims, their_fielding=their_fielding, scope=scope,
    )


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _assemble(*, our_name, opp_key, opp_name, player_id, player_name, games_total, checked, no_card,
              played, bat_inns, spells, got_them_out, fielded_them, victims, their_fielding, scope) -> dict:
    played.sort(key=lambda x: x["date"] or "", reverse=True)
    us = our_name or "us"

    # ── their batting against us ──
    batting = None
    if bat_inns:
        runs = sum(i["runs"] for i in bat_inns)
        outs = sum(1 for i in bat_inns if not i["not_out"])
        with_balls = [i for i in bat_inns if i["balls"]]
        sr_runs = sum(i["runs"] for i in with_balls)
        sr_balls = sum(i["balls"] for i in with_balls)
        hs = max(bat_inns, key=lambda i: (i["runs"], i["not_out"]))
        dism = Counter(i["dismissal"] for i in bat_inns if i["dismissal"])
        batting = {
            "innings": len(bat_inns), "runs": runs, "not_outs": len(bat_inns) - outs,
            "average": round(runs / outs, 2) if outs else None,
            "strike_rate": round(100 * sr_runs / sr_balls, 2) if sr_balls else None,
            "high_score": f"{hs['runs']}{'*' if hs['not_out'] else ''}",
            "fifties": sum(1 for i in bat_inns if 50 <= i["runs"] < 100),
            "hundreds": sum(1 for i in bat_inns if i["runs"] >= 100),
            "ducks": sum(1 for i in bat_inns if i["runs"] == 0 and not i["not_out"]),
            "dismissals": [{"type": t, "count": c, "pct": round(100 * c / outs)} for t, c in dism.most_common()] if outs else [],
            "outs": outs,
        }

    # ── their bowling against us ──
    bowling = None
    if spells:
        wk = sum(s["wickets"] for s in spells)
        rn = sum(s["runs"] for s in spells)
        bl = sum(s["balls"] for s in spells)
        best = max(spells, key=lambda s: (s["wickets"], -s["runs"]))
        bowling = {
            "spells": len(spells), "wickets": wk, "runs": rn, "overs": _balls_to_overs(bl),
            "maidens": sum(s["maidens"] for s in spells),
            "average": round(rn / wk, 2) if wk else None,
            "economy": round(rn / (bl / 6), 2) if bl else None,
            "strike_rate": round(bl / wk, 1) if wk else None,
            "best": f"{best['wickets']}/{best['runs']}",
        }

    got = _finish(got_them_out)
    fld = _finish(fielded_them)
    vic = _finish(victims)
    tfld = _finish(their_fielding)

    # ── the quick read: rule-based, neutral wording ──
    lines: list[str] = []
    if batting:
        avg = f"{batting['average']:.2f}" if batting["average"] is not None else "no dismissal yet"
        lines.append(
            f"{_plural(batting['runs'], 'run')} against {us} from {_plural(batting['innings'], 'innings', 'innings')}"
            f" (average {avg}, best {batting['high_score']})."
        )
        if got and got[0]["count"] >= 2:
            top = got[0]
            lines.append(f"{top['name']} has dismissed them {top['count']} times out of {batting['outs']}.")
        catchers = [f for f in fld if f.get("catches")]
        if catchers and catchers[0]["catches"] >= 2:
            lines.append(f"{catchers[0]['name']} has caught them {catchers[0]['catches']} times.")
        if batting["outs"] >= 3 and batting["dismissals"]:
            top_d = batting["dismissals"][0]
            if top_d["pct"] >= 50:
                lines.append(f"{top_d['pct']}% of their dismissals against {us} are {top_d['type']}.")
    if bowling and bowling["wickets"]:
        avg = f"{bowling['average']:.2f}" if bowling["average"] is not None else "n/a"
        lines.append(f"{_plural(bowling['wickets'], 'wicket')} against {us} at {avg}, best {bowling['best']}.")
        if vic and vic[0]["count"] >= 2:
            lines.append(f"{vic[0]['name']} has fallen to them {vic[0]['count']} times.")
    if played and len(played) <= 2:
        lines.append(f"Small sample: {_plural(len(played), 'game')} against {us} so far, so treat these as hints.")

    notes = []
    if games_total:
        capped = games_total > MAX_VS_US_GAMES
        notes.append(
            f"Checked {'the most recent ' + str(min(games_total, MAX_VS_US_GAMES)) + ' of ' if capped else ''}"
            f"{_plural(games_total, 'game')} {our_name or 'our club'} has played against "
            f"{opp_name or 'this club'}; this player appeared in {len(played)}."
        )
    if no_card:
        notes.append(f"{_plural(no_card, 'game')} had no Cricket Australia scorecard (hand-entered or not on PlayHQ) and could not be read.")
    notes.append("Dismissals, catches and wickets come from the scorecards. We hold no ball-by-ball data, so there are no head-to-head ball counts.")

    return {
        "player": {"player_id": player_id, "name": player_name},
        "opponent": {"opp_key": opp_key, "name": opp_name},
        "us": {"name": our_name},
        "scope": scope,
        "games_total": games_total,
        "games_checked": checked,
        "games_played": len(played),
        "batting": batting,
        "bowling": bowling,
        "got_them_out": got,
        "fielded_them": fld,
        "victims": vic,
        "their_fielding": tfld,
        "games": played,
        "lines": lines,
        "notes": notes,
        "schema_v": VS_US_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_or_start_player_vs_us(
    session: AsyncSession, our_org_id: str, our_name: str | None, opp_key: str, player_id: str,
    *, player_name: str | None = None, opp_name: str | None = None, force: bool = False,
) -> dict:
    """One opposition player's record against our club. Background build and
    poll (``building`` until ready), cached 7 days like the deep scan."""
    opp_key = (opp_key or "").strip()
    player_id = (player_id or "").strip()
    if not opp_key or not player_id:
        return {"status": "unavailable", "message": "Pick a club and a player first."}
    opp_org_id = opp_key if _is_uuid(opp_key) else None
    opp_name = opp_name or (None if opp_org_id else opp_key)
    games = await _our_games_vs(session, our_org_id, opp_key)
    scope = _scope_labels()
    if not games:
        # Nothing to read: answer at once and say why, rather than build.
        return {"status": "ready", **_assemble(
            our_name=our_name, opp_key=opp_key, opp_name=opp_name, player_id=player_id,
            player_name=player_name, games_total=0, checked=0, no_card=0, played=[], bat_inns=[],
            spells=[], got_them_out={}, fielded_them={}, victims={}, their_fielding={}, scope=scope,
        )}
    ours = await _our_player_ids(session, our_org_id)
    games = [
        {**g, "played_at": g["played_at"].isoformat() if isinstance(g.get("played_at"), (date, datetime)) else g.get("played_at")}
        for g in games
    ]
    return await _get_or_start(
        session, our_org_id, _cache_key(opp_key, player_id), VS_US_VERSION,
        lambda: _build(our_org_id, our_name, opp_key, opp_org_id, opp_name, player_id, player_name,
                       games, ours, scope),
        name=player_name, force=force,
    )
