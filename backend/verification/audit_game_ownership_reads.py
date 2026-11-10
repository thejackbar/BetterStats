"""Game ownership audit: no new per-game read decides "whose game" from the season's owner.

A game belongs to no club. A fixture two synced clubs played is ONE `games` row, and its
`grade_id` (so its season) is the grade row of whichever club's sync created it first. A read
that decides "this game is ours" or "this game is in our season" from that row's owner
(`seasons.organisation_id = :org`, `Season.organisation_id ==`, `Grade.season_id == <our season>`,
or the view's `g.organisation_id` on its own) drops the club's half of every such fixture. That
has been fixed, again, in Fees, StatLab, the Club records tab, the admin Games list, the
scorecard duplicate check, public Lineups and two BetterIQ clauses (v9.142.3.2 and v9.142.4).

This audit is static (no database). For every function under backend/app it joins all the string
literals in the function and flags it when ALL of these hold:
  * it reads a per-game table or view (games, v_effective_games, batting_innings, bowling_spells,
    fielding_stats, game_appearances, partnerships, ...) or the ORM `Game`,
  * it scopes by the owner (an owner-only expression above), and
  * it uses none of the shared answers: `club_game_sql` / `club_game_clause` / `_OURS_GAMES`,
    the `home_org_id` / `away_org_id` sides, `include_shared` or a `cross_club` season clause,
    `game_universe`, `club_grade_rows`, `fees._season_games`.

A second rule catches the other half of the same bug: every call to
`season_aliases.resolve_season_filter(...)` must pass `include_shared=True` (the other clubs' rows of
the same real-world season) or be on SEASON_BASELINE with the reason it never touches a game. A
season list that only holds the club's own rows is how StatLab, the Club records tab and a BetterIQ
clause lost a game the moment a season was picked.

A flagged function is fine only when it is on BASELINE below with the reason. The baseline is the
backlog of sites an audit confirmed and nobody has fixed yet, plus the ones judged deliberate. It
only shrinks:

    python -m verification.audit_game_ownership_reads

Fails (exit 1) when
  * a function is flagged and is not on the baseline (a new owner-only game read), or
  * a baselined function is no longer flagged or no longer exists (delete the entry; a stale
    entry hides the next function that reuses the name).

How to fix a flagged function: "ours" is `services/club_grades.club_game_sql` (owner OR home/away
side); the season is `season_aliases.resolve_season_filter(..., include_shared=True)` or
`iq_filters.season_member_clause_cross_club`; scope the PLAYER with `players.organisation_id`; a
win or loss is re-derived from `winning_team` against our side, never read from `games.result`.
Then prove it on `verification/verify_shared_fixture_reads.py` style data: two clubs, one season
held under each club's own row, one game under each, with a control run on the previous commit.

The scan is a tripwire, not a proof: a function that uses a safe marker anywhere is passed, and a
read built outside a function (a module-level SQL string) is not seen.
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "app"
SKIP_PARTS = ("/scripts/", "/afl/", "afl_main.py")

GAME_READ = re.compile(
    r"\b(FROM|JOIN)\s+(v_effective_games|games|v_effective_batting_innings|v_effective_bowling_spells"
    r"|v_effective_fielding_stats|batting_innings|bowling_spells|fielding_stats|game_appearances"
    r"|partnerships|fall_of_wickets|bowler_wickets)\b|\bselect\(\s*Game\b|\bjoin\(\s*Game\b|\bGame\.\w+",
    re.I)
OWNER = re.compile(
    r"\b(s|se|s2|ps|sn|seasons)\.organisation_id\s*=|Season\.organisation_id\s*=="
    r"|Grade\.season_id\s*(==|\.in_\()|\bg\.organisation_id\s*=", re.I)
SAFE = re.compile(
    r"home_org_id|away_org_id|club_game_sql|club_game_clause|CLUB_GAME_SQL|_OURS_GAMES|_club_game_clause"
    r"|game_universe|include_shared|cross_club|club_grade_rows|_season_games|_ours_clause|_OWN_PRED"
    r"|_OWNS_GAME|our_games|_OG_CTE", re.I)

CONFIRMED = "CONFIRMED, not yet fixed: drops a game stored under another club's season row"
DESTRUCTIVE = "DECISION NEEDED: deletes whole shared games, and with them the other club's rows"
DELIBERATE = "deliberate / not a game read"
TO_CHECK = "not yet checked: flagged by the scan only"

# (file relative to backend/app, function) -> why it is allowed to stay.
BASELINE: dict[tuple[str, str], str] = {
    # ---- admin and import screens
    ("routers/admin.py", "list_grades_with_stats"): CONFIRMED + " (a grade's game count; players also unscoped)",
    ("routers/admin.py", "apply_grade_suggestions"): DELIBERATE + ": the club's own grades",
    ("routers/club_admin.py", "list_grades"): DELIBERATE + ": the club's own grades",
    ("routers/club_admin.py", "_do_import_partnership_records"): CONFIRMED + " (duplicate check misses a stand synced under the other club's season, so an import adds it twice)",
    ("routers/club_admin.py", "preview_club_merge"): DELIBERATE + ": counts what an org merge moves, anchored on the row's owner",
    ("routers/club_admin.py", "list_milestones_report"): DELIBERATE + ": scoped by the club's players",
    ("routers/club_admin.py", "hard_refresh_org"): DESTRUCTIVE + " (HardRefresh wipe)",
    ("routers/club_admin.py", "_run"): DESTRUCTIVE + " (HardRefresh wipe, nested in hard_refresh_org)",
    ("routers/imports.py", "_org_grade_options"): CONFIRMED + " (grade game counts on the import match screen)",
    ("routers/manual_entries.py", "commit_manual_games"): TO_CHECK + " (re-source warning counts only)",
    ("routers/teams.py", "seed_candidates"): CONFIRMED + " (auto-seed picker)",
    ("routers/teams.py", "auto_assign_suggest"): CONFIRMED + " (squad appearance counts)",
    ("services/cricketstatz_import.py", "synced_coverage"): CONFIRMED + " (import preview undercounts synced years)",
    ("services/crm.py", "hard_delete_registered_club"): DESTRUCTIVE + " (club hard delete cascades through games under its season rows)",
    # ---- public yearbook (32 statements across these functions)
    ("routers/yearbooks.py", "get_overview"): CONFIRMED + " (yearbook W/L, and grade filters)",
    ("routers/yearbooks.py", "get_superlatives"): CONFIRMED,
    ("routers/yearbooks.py", "get_match_results"): CONFIRMED,
    ("routers/yearbooks.py", "get_season_milestones"): CONFIRMED + " (season date window only)",
    ("routers/yearbooks.py", "get_grade_breakdown"): CONFIRMED,
    ("routers/yearbooks.py", "_generate_narrative_core"): CONFIRMED + " (the auto-published narrative)",
    # ---- records, aggregations, grade labels, milestones
    ("routers/records.py", "get_records_milestones"): CONFIRMED + " (renamed-grade match copied from aggregations._GRADE_MATCH)",
    ("services/aggregations.py", "get_batting_by_grade"): TO_CHECK + " (reviewer: scoped by player only; gr.is_public may hide our half)",
    ("services/aggregations.py", "get_bowling_by_grade"): TO_CHECK + " (reviewer: scoped by player only; gr.is_public may hide our half)",
    ("services/aggregations.py", "get_player_team_breakdown"): DELIBERATE + ": its own folding pass (guide rule 31)",
    ("services/grade_labels.py", "org_grade_format_sets"): CONFIRMED + " (formats seen only on the club's own grade rows)",
    ("services/grade_scope.py", "player_categories"): TO_CHECK,
    ("services/milestone_totals.py", "played_grade_names"): CONFIRMED + " (a game under another club's grade row is not classified)",
    ("services/player_cards.py", "_current_season"): TO_CHECK,
    ("services/scout_internal_link.py", "internal_match_log"): CONFIRMED + " (season and year come back NULL for a shared game)",
    ("services/sync.py", "_backfill_missing_season_stats"): TO_CHECK + " (writes aggregates into the club's own season)",
    # ---- BetterIQ
    ("services/iq.py", "list_opponents"): CONFIRMED + " (opponent identity is stamped from the first syncer's side)",
    ("services/iq.py", "_resolve_opp_key"): CONFIRMED,
    ("services/iq.py", "_head_to_head"): CONFIRMED,
    ("services/iq.py", "_our_performers_vs"): CONFIRMED,
    ("services/iq.py", "_their_danger_batters"): CONFIRMED,
    ("services/iq.py", "search_opponent_players"): CONFIRMED,
    ("services/iq.py", "_venues_vs"): CONFIRMED,
    ("services/iq.py", "_our_bowler_dominance"): CONFIRMED,
    ("services/iq.py", "_last_meeting"): CONFIRMED,
    ("services/iq_opponent.py", "_synced_opponent_org"): CONFIRMED,
    ("services/iq_opponent.py", "_db_season_accumulators"): CONFIRMED,
    ("services/iq_opponent.py", "_target_season_id"): CONFIRMED,
    ("services/iq_phases.py", "team_phases"): CONFIRMED,
    ("services/iq_phases.py", "opponent_phases"): CONFIRMED,
    ("services/iq_team.py", "team_grades"): DELIBERATE + ": a dropdown of the club's own grades",
    ("services/iq_team.py", "_partnerships"): CONFIRMED,
    ("services/iq_team.py", "_team_fielding"): CONFIRMED,
    ("services/iq_team.py", "_all_rounders"): CONFIRMED,
    ("services/iq_team.py", "_batting_pairs"): CONFIRMED,
    ("services/iq_team.py", "_attack_structure"): CONFIRMED,
    ("services/iq_team.py", "_collapses"): CONFIRMED,
    ("services/iq_team.py", "_combinations"): CONFIRMED,
    ("services/iq_team.py", "pair_synergy"): CONFIRMED,
    ("services/iq_team.py", "_discipline"): CONFIRMED,
    ("services/iq_team.py", "_wickets_quality"): CONFIRMED,
    ("services/iq_team.py", "_collapse_bowlers"): CONFIRMED,
    ("services/iq_team.py", "_team_starts"): CONFIRMED,
    ("services/iq_team.py", "_role_ratings"): CONFIRMED,
    ("services/iq_team.py", "_batting_extra"): CONFIRMED,
}


# (file, function) -> why this resolve_season_filter call may stay own-club only.
SEASON_BASELINE: dict[tuple[str, str], str] = {
    ("services/aggregations.py", "get_player_rankings"): "ranks season AGGREGATE rows (v_effective_player_season_stats), no game read",
    ("routers/organisations.py", "get_org_grades"): "a dropdown of the club's own grade names, no game read",
}


def _season_calls_without_shared(tree: ast.AST, rel: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call):
                continue
            name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
            if name != "resolve_season_filter":
                continue
            shared = any(k.arg == "include_shared" for k in call.keywords) or len(call.args) >= 4
            if not shared:
                out.add((rel, fn.name))
    return out


def _strings(node: ast.AST) -> str:
    return "\n".join(n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str))


def scan() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    found: set[tuple[str, str]] = set()
    season_found: set[tuple[str, str]] = set()
    for f in sorted(ROOT.rglob("*.py")):
        rel = f.relative_to(ROOT).as_posix()
        if any(x in "/" + rel for x in SKIP_PARTS):
            continue
        src = f.read_text()
        lines = src.splitlines()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        season_found |= _season_calls_without_shared(tree, rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = "\n".join(lines[node.lineno - 1: node.end_lineno])
                blob = _strings(node) + "\n" + body
                if GAME_READ.search(blob) and OWNER.search(blob) and not SAFE.search(blob):
                    found.add((rel, node.name))
    return found, season_found


def main() -> int:
    found, season_found = scan()
    new = sorted(found - set(BASELINE))
    stale = sorted(set(BASELINE) - found)
    season_new = sorted(season_found - set(SEASON_BASELINE))
    season_stale = sorted(set(SEASON_BASELINE) - season_found)
    bad = False
    if season_new:
        bad = True
        print("resolve_season_filter(...) without include_shared (the other clubs' rows of the season are dropped):")
        for rel, fn in season_new:
            print(f"  {rel}  {fn}")
        print("  Pass include_shared=True where the read is also guarded by club_game_sql or the club's players, "
              "or add the function to SEASON_BASELINE with the reason it never touches a game.")
    if season_stale:
        bad = True
        print("STALE SEASON_BASELINE entries: delete them.")
        for rel, fn in season_stale:
            print(f"  {rel}  {fn}")
    if new:
        bad = True
        print("NEW owner-only game reads (not on the baseline):")
        for rel, fn in new:
            print(f"  {rel}  {fn}")
        print("  Use club_game_sql for 'ours' and resolve_season_filter(..., include_shared=True) for the season "
              "(see this file's docstring), or add the function to BASELINE with the reason it is safe.")
    if stale:
        bad = True
        print("STALE baseline entries (no longer flagged or no longer exist): delete them.")
        for rel, fn in stale:
            print(f"  {rel}  {fn}  [{BASELINE[(rel, fn)][:60]}]")
    todo = sum(1 for v in BASELINE.values() if v.startswith("CONFIRMED"))
    decisions = sum(1 for v in BASELINE.values() if v.startswith("DECISION"))
    unchecked = sum(1 for v in BASELINE.values() if v.startswith("not yet checked"))
    print(f"{len(found)} flagged function(s): {todo} confirmed and unfixed, {decisions} needing a decision, "
          f"{unchecked} not yet checked, {len(found) - todo - decisions - unchecked} deliberate"
          + ("" if not bad else " | FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
