"""Clubs that searched for themselves or picked themselves in the registration
wizard, as one outreach list.

The Meta Ads page reports these as two separate tables — "Clubs selected in the
wizard" (they clicked into the wizard) and "Clubs searched in the wizard" (they
typed the name and got a result but never clicked). Both are the same kind of
warm prospect and both want the same follow-up, so this merges them into one
row per club and hangs the outreach machinery off it.

Three things happen here:

  1. **Merge** the two sides on their shared normalised-name key. The selected
     side is ``meta_ads.get_selected_clubs`` as-is. The searched side is
     resolved HERE (``resolved_searched_clubs``) rather than read off
     ``meta_ads.get_searched_clubs``: that table reports each beacon's raw top
     match, which is close to arbitrary for a half-typed query, and this page
     emails people. The Meta Ads page keeps its own reporting untouched — the
     two are allowed to disagree, and nothing here writes back.
  2. **Match** each one to a Club Directory club, so we know who to email. The
     wizard's own beacon captures the club's real CA organisation guid, which is
     the same guid the PlayHQ crawler keys the directory on — so that is the
     first match, with a case-insensitive name match as the fallback for a row
     that predates the guid being captured.
  3. **Report** whether the club has been emailed since. Derived, never stored:
     a campaign carries its audience ``list_id``, a sent ``comms_recipients``
     row carries its contact, and a ``comms_contacts`` row exported from the
     directory carries its ``marketing_club_id``. Join those three and a club's
     whole send history falls out, so it self-corrects and there is no
     send-path hook to keep in step.

Creating a list follows the Club Directory's own export rules
(``club_directory.export_to_comms``) rather than inventing a second set: never
export an excluded club, never export a contact that has opted out, link every
new contact back to its directory club so ``{{club}}`` and the per-recipient
unsubscribe resolve, and stamp ``exported_at`` so the Directory's own badge
stays accurate.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CommsContact, CommsList, CommsListMember, MarketingClub, MarketingClubContact,
    WizardClubList,
)
from app.services.marketing_org import get_outreach_org

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# What an un-named generic club mailbox (info@, secretary@, the crawler's own
# club-level contact_email) is greeted as. A club address is read by whoever is
# on the committee this year, so the merge variable has to address the group —
# leaving it blank produces "Hi ," and guessing a person's name would be a lie.
GENERIC_FIRST_NAME = "Committee Members"
ORIGIN_LABEL = "Wizard Clubs"


def norm_key(name: Optional[str]) -> str:
    """The wizard tables' own grouping key — see meta_ads.get_selected_clubs,
    which sets ``key`` to the stripped, lowercased club name."""
    return (name or "").strip().lower()


def norm_email(raw: Optional[str]) -> Optional[str]:
    e = (raw or "").strip().lower()
    return e if _EMAIL_RE.match(e) else None


def _first_name(full: Optional[str]) -> str:
    return (full or "").strip().split()[0] if (full or "").strip() else ""


def _iso(v):
    return v.isoformat() if v is not None and hasattr(v, "isoformat") else v


def _later(a, b):
    """Max of two ISO strings, either of which may be None."""
    if a and b:
        return a if a >= b else b
    return a or b


def _earlier(a, b):
    """Min of two ISO strings, either of which may be None."""
    if a and b:
        return a if a <= b else b
    return a or b


# ── What was this person actually searching for? ─────────────────────────────
#
# `meta_ads.get_searched_clubs` groups the `club_searched` beacons on the TOP
# result each search returned, which for a half-typed query is close to
# arbitrary: "Warn" surfaced "CNSW WWCF Program - Warners Bay", "Warnbro"
# surfaced "WA Cricket Programs - Warnbro Community High School", and the person
# was typing their way to Warnbro Swans Cricket Club the whole time. Taken at
# face value that is two prospect clubs nobody ever searched for, plus one real
# club split across three rows.
#
# THIS PAGE resolves the same beacons itself rather than reading that table,
# because it is the page that acts on them — it matches a club to the Club
# Directory and emails its committee, so a guessed club here is an email to the
# wrong people. The Meta Ads page keeps its own reporting exactly as it is; the
# two are deliberately allowed to disagree, and this module never writes
# anything back.
#
# Two rules, and the first does the heavy lifting:
#
#   1. One person typing one club name is ONE search, not six. A visitor's
#      consecutive searches where each query extends or trims the last (the
#      signature of typing, and of backspacing) collapse into a single run,
#      resolved by the most specific thing they typed — and outright by the club
#      they went on to select, when they selected one.
#   2. A query that does not identify the club it matched is reported as the
#      QUERY, with the match named only as a guess. "Warn" matching a club
#      called "…Warners Bay" is a hit on a word buried mid-name, not evidence of
#      intent; "warnbro swa" against "Warnbro Swans Cricket Club" is.

# How far apart two searches can be and still be the same person typing. Seconds
# in practice; generous here because a search box left open while someone finds
# their club's proper name is still one intent, not two.
_SEARCH_RUN_GAP = timedelta(minutes=30)
# A picked club counts as confirming a run it lands within, plus this much
# slack — the click follows the last keystroke, never precedes it by much.
_SELECT_SLACK = timedelta(minutes=30)
# Below this, a query is too little to identify anyone. Four characters matched
# three unrelated clubs in the reported case.
_MIN_IDENTIFYING_QUERY = 4
# Strongest evidence wins when several runs pool into one row.
_CONFIDENCE_RANK = {"unsure": 0, "likely": 1, "confirmed": 2}


def _norm_query(raw: Optional[str]) -> str:
    """Lowercased, punctuation flattened to single spaces — so "St Mary's CC"
    and "st marys cc" compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", (raw or "").lower()).strip()


def _same_typing_run(prev: Optional[str], cur: Optional[str]) -> bool:
    """True when one query is a prefix of the other — typing forward
    ("warn" → "warnb") or backspacing ("warnbro swa" → "warnbro sw")."""
    a, b = _norm_query(prev), _norm_query(cur)
    if not a or not b:
        return False
    return a.startswith(b) or b.startswith(a)


def _query_identifies(query: Optional[str], club_name: Optional[str]) -> bool:
    """Does this query actually pick out this club, or did it merely match
    somewhere inside the name?

    The test is that the club's name STARTS with what was typed. That is what
    separates "warnbro swa" → "Warnbro Swans Cricket Club" (the person was
    typing this club's name) from "warn" → "CNSW WWCF Program - Warners Bay"
    (a hit on a word buried in the middle, which the searcher never aimed at).
    """
    q, n = _norm_query(query), _norm_query(club_name)
    if not q or not n or len(q) < _MIN_IDENTIFYING_QUERY:
        return False
    return n.startswith(q)


def _query_is_ambiguous(query: Optional[str], known_names: set) -> bool:
    """True when what was typed is the start of more than one club we have
    seen, so identifying it with any single one of them is a coin toss.

    _query_identifies alone is not enough: "south" genuinely is the start of
    "Southern Cricket Club", but it is equally the start of "Southern Districts
    CC", and the beacon only ever recorded whichever the search ranked first.
    The names checked against are the clubs these beacons themselves surfaced —
    the only universe this data can see."""
    q = _norm_query(query)
    if not q:
        return True
    return len({n for n in known_names if _norm_query(n).startswith(q)}) > 1


def _run_row(name, org_id, queries, run, first_at, last_at, via_meta,
             confidence, guess_name, guess_org_id) -> dict:
    return {
        "name": name,
        # An unsure run is keyed on the query, never on a club — two guesses at
        # the same club must not merge into a prospect row nobody searched for.
        "key": (f"search:{_norm_query(name)}" if confidence == "unsure"
                else (name or "").strip().lower()),
        "org_id": org_id,
        "visitor_id": run[0]["visitor_id"],
        "queries": queries,
        "searches": len(run),
        "via_meta": via_meta,
        "confidence": confidence,
        "is_query_row": confidence == "unsure",
        "guess_name": guess_name,
        "guess_org_id": guess_org_id,
        "guess_from_confirmed": False,
        "first_at": first_at,
        "last_at": last_at,
    }


def _resolve_run(run: list[dict], picks: list[dict], known_names: set) -> dict:
    """One typing run → the club behind it, plus how sure we are.

    Preference order: the club the visitor actually clicked during the run
    (certain), then a search that returned exactly one club, then the top match
    for the most specific query typed — reported as a real club only when that
    query uniquely identifies it, and otherwise as the query itself with the
    match carried alongside as a guess."""
    # The most specific thing typed. Ties (a backspace landing on an equally
    # long earlier query) go to the later one.
    best = max(run, key=lambda r: (len(r["query"] or ""), r["created_at"]))
    top_name = (best["club_name"] or "").strip()
    top_org = best["org_id"]

    queries, seen = [], set()
    for r in run:
        q = (r["query"] or "").strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)

    first_at = min(r["created_at"] for r in run)
    last_at = max(r["created_at"] for r in run)
    via_meta = any(bool(r["via_meta"]) for r in run)

    # 1. Did they click a club around this run? That settles it — whatever they
    #    typed, the club they opened is the club they wanted. Guarded so a
    #    selection from an unrelated run can't hijack this one: it has to be
    #    either the club the search surfaced, or one the typing was plainly
    #    heading towards.
    for p in picks:
        if not (first_at - _SELECT_SLACK <= p["at"] <= last_at + _SELECT_SLACK):
            continue
        picked = (p["name"] or "").strip()
        if not picked:
            continue
        if picked.lower() == top_name.lower() or _query_identifies(best["query"], picked):
            return _run_row(picked, p["org_id"] or top_org, queries, run,
                            first_at, last_at, via_meta, "confirmed", None, None)

    # 2. A search that returned exactly one club named that club, whatever was
    #    typed to get there. Only known for beacons sent since result_count
    #    started being recorded; NULL for every earlier one.
    if best.get("result_count") == 1 and top_name:
        return _run_row(top_name, top_org, queries, run, first_at, last_at,
                        via_meta, "likely", None, None)

    # 3. Otherwise trust the match only when the query identifies it AND
    #    identifies it uniquely — a query that fits several clubs picks none.
    if (top_name and _query_identifies(best["query"], top_name)
            and not _query_is_ambiguous(best["query"], known_names)):
        return _run_row(top_name, top_org, queries, run, first_at, last_at,
                        via_meta, "likely", None, None)

    # 4. We genuinely don't know. Report the search, name the match as a guess.
    label = (best["query"] or "").strip() or top_name
    return _run_row(label, None, queries, run, first_at, last_at, via_meta,
                    "unsure", top_name or None, top_org)


def _collapse_search_runs(rows: list[dict], picks_by_visitor: dict,
                          known_names: set) -> list[dict]:
    """Fold a visitor's raw `club_searched` beacons into one entry per typing
    run. ``rows`` must be ordered by visitor then time."""
    runs: list[dict] = []
    current: list[dict] = []

    def _flush():
        if current:
            runs.append(_resolve_run(list(current),
                                     picks_by_visitor.get(current[0]["visitor_id"], []),
                                     known_names))
            current.clear()

    for r in rows:
        if current:
            prev = current[-1]
            # A beacon with no visitor_id can't be grouped with anything — it
            # stands alone rather than being folded into a stranger's typing.
            same_visitor = (r["visitor_id"] is not None
                            and prev["visitor_id"] == r["visitor_id"])
            in_window = (r["created_at"] - prev["created_at"]) <= _SEARCH_RUN_GAP
            if not (same_visitor and in_window and _same_typing_run(prev["query"], r["query"])):
                _flush()
        current.append(r)
    _flush()
    return runs


def _improve_guesses(rows: list[dict]) -> None:
    """Give an unresolved query a better guess than its arbitrary top match.

    Once the confident rows are known, an unresolved query is often the start
    of one of them — "warn" against a "Warnbro Swans Cricket Club" someone else
    typed out in full. When EXACTLY ONE confident club's name begins with the
    query, that beats whatever the search engine happened to rank first. Two or
    more and the query genuinely doesn't pick a club, so the guess is dropped
    rather than a coin toss being presented as an answer. Mutates in place, and
    only ever touches the guess — an unsure row stays unsure and stays keyed on
    its query, so it can never be mistaken for a club we stand behind."""
    confident = [c for c in rows if not c["is_query_row"]]
    if not confident:
        return
    for c in rows:
        if not c["is_query_row"]:
            continue
        q = _norm_query(c["name"])
        if not q:
            continue
        hits = [k for k in confident if _norm_query(k["name"]).startswith(q)]
        if len(hits) == 1:
            c["guess_name"] = hits[0]["name"]
            c["guess_org_id"] = hits[0]["org_id"]
            c["guess_from_confirmed"] = True
        elif len(hits) > 1:
            c["guess_name"] = None
            c["guess_org_id"] = None


async def resolved_searched_clubs(session: AsyncSession, days: int) -> list[dict]:
    """The wizard's `club_searched` beacons, resolved to the clubs people were
    actually after — this page's own read of the same rows the Meta Ads page
    reports raw. See the rules above for why it can't just group on the top
    match. Returns one row per resolved club (or per unresolved query), in the
    same shape ``merged_wizard_clubs`` expects from the selected side."""
    from app.services import meta_ads

    window = {"days": days}

    # Raw beacons, ordered so one visitor's typing reads as the sequence it was.
    # `result_count` is regex-matched before casting: the metadata blob is
    # free-form, and one junk value would abort the cast for every row.
    raw = (await session.execute(text(f"""
        SELECT visitor_id::text                            AS visitor_id,
               metadata->>'club_name'                      AS club_name,
               metadata->>'club_org_id'                    AS org_id,
               NULLIF(TRIM(metadata->>'search_query'), '') AS query,
               CASE WHEN metadata->>'result_count' ~ '^[0-9]+$'
                    THEN (metadata->>'result_count')::int END AS result_count,
               created_at,
               {meta_ads._META_VISITOR_SUBQUERY_PLAIN}     AS via_meta
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND route = 'club_searched'
          AND created_at >= NOW() - (:days * INTERVAL '1 day')
          AND NULLIF(TRIM(metadata->>'club_name'), '') IS NOT NULL
        ORDER BY visitor_id, created_at
    """), window)).mappings().all()

    # Every club a visitor actually clicked into, so a run can be settled by
    # what they picked rather than by what they had typed so far.
    pick_rows = (await session.execute(text("""
        SELECT visitor_id::text         AS visitor_id,
               metadata->>'club_name'   AS name,
               metadata->>'club_org_id' AS org_id,
               created_at               AS at
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND route = 'club_prepared'
          AND created_at >= NOW() - (:days * INTERVAL '1 day')
          AND NULLIF(TRIM(metadata->>'club_name'), '') IS NOT NULL
    """), window)).mappings().all()
    picks_by_visitor: dict = {}
    for p in pick_rows:
        picks_by_visitor.setdefault(p["visitor_id"], []).append(dict(p))

    # Every club these beacons surfaced — the yardstick for whether a query
    # picks out one club or several.
    known_names = {(r["club_name"] or "").strip() for r in raw if r["club_name"]}
    known_names |= {(p["name"] or "").strip() for p in pick_rows if p["name"]}
    known_names.discard("")

    runs = _collapse_search_runs([dict(r) for r in raw], picks_by_visitor, known_names)
    selected_keys = {(p["name"] or "").strip().lower() for p in pick_rows if p["name"]}

    merged: dict = {}
    for run in runs:
        key = run["key"]
        if not key or key == "search:":
            continue
        c = merged.get(key)
        if c is None:
            merged[key] = c = {
                "name": run["name"], "key": key, "org_id": run["org_id"],
                "visitors": set(), "searches": 0, "queries": [], "via_meta": False,
                "confidence": run["confidence"], "is_query_row": run["is_query_row"],
                "guess_name": run["guess_name"], "guess_org_id": run["guess_org_id"],
                "guess_from_confirmed": False,
                "first_at": run["first_at"], "last_at": run["last_at"],
            }
        c["visitors"].add(run["visitor_id"])
        c["searches"] += run["searches"]
        c["via_meta"] = c["via_meta"] or run["via_meta"]
        c["org_id"] = c["org_id"] or run["org_id"]
        # Best evidence across the runs wins — one visitor confirming the club
        # settles it for everyone who only half-typed the same name.
        if _CONFIDENCE_RANK[run["confidence"]] > _CONFIDENCE_RANK[c["confidence"]]:
            c["confidence"] = run["confidence"]
        for q in run["queries"]:
            if q not in c["queries"]:
                c["queries"].append(q)
        c["first_at"] = min(c["first_at"], run["first_at"])
        c["last_at"] = max(c["last_at"], run["last_at"])

    rows: list[dict] = []
    for c in merged.values():
        # A beacon with no visitor_id still represents someone searching.
        c["visitors"] = len([v for v in c["visitors"] if v is not None]) or 1
        c["queries"] = c["queries"][:5]
        c["selected"] = (not c["is_query_row"]) and c["key"] in selected_keys
        c["first_at"] = _iso(c["first_at"])
        c["last_at"] = _iso(c["last_at"])
        rows.append(c)

    _improve_guesses(rows)

    # Test noise a super admin flagged on the Meta Ads selected-clubs table is
    # test noise here too — same normalised-name key, one place to flag it.
    from app.services import platform_settings
    hidden_keys = await platform_settings.get_hidden_meta_selections(session)
    return [c for c in rows if c["key"] not in hidden_keys]


# ── merge the two Meta Ads tables ────────────────────────────────────────────

async def merged_wizard_clubs(session: AsyncSession, days: int) -> list[dict]:
    """One row per club across the selected AND searched wizard tables, keyed on
    the normalised name both already group by. A club present in both is one
    row carrying both sets of facts."""
    from app.services import meta_ads

    selected = await meta_ads.get_selected_clubs(session, days)
    # The searched side is resolved HERE, not read off meta_ads.get_searched_clubs
    # — that table reports each beacon's raw top match, which this page must not
    # act on. See resolved_searched_clubs above.
    searched_rows = await resolved_searched_clubs(session, days)

    rows: dict[str, dict] = {}

    def _row(key: str, name: str) -> dict:
        return rows.setdefault(key, {
            "key": key, "name": name, "org_id": None,
            "in_selected": False, "in_searched": False,
            "furthest_step": "", "visitors": 0, "searches": 0, "queries": [],
            "via_meta": False, "first_at": None, "last_at": None,
            # Set only by the searched side — a row we could not resolve to a
            # club is the raw query, with the best guess carried alongside.
            "is_query_row": False, "confidence": "", "guess_name": None,
        })

    for c in (selected.get("clubs") or []):
        r = _row(c.get("key") or norm_key(c.get("name")), (c.get("name") or "").strip())
        r["in_selected"] = True
        r["org_id"] = r["org_id"] or c.get("org_id")
        r["furthest_step"] = c.get("furthest_step") or r["furthest_step"]
        r["visitors"] = max(r["visitors"], int(c.get("visitors") or 0))
        r["via_meta"] = r["via_meta"] or bool(c.get("via_meta"))
        r["first_at"] = _earlier(r["first_at"], c.get("first_at"))
        r["last_at"] = _later(r["last_at"], c.get("last_at"))

    for c in searched_rows:
        r = _row(c.get("key") or norm_key(c.get("name")), (c.get("name") or "").strip())
        r["in_searched"] = True
        r["org_id"] = r["org_id"] or c.get("org_id")
        r["visitors"] = max(r["visitors"], int(c.get("visitors") or 0))
        r["searches"] = max(r["searches"], int(c.get("searches") or 0))
        r["queries"] = r["queries"] or list(c.get("queries") or [])
        r["via_meta"] = r["via_meta"] or bool(c.get("via_meta"))
        # A search we could not pin to a club (see _resolve_run above) is a
        # QUERY, not a club — it must never be matched against the directory or
        # exported, so the flag travels with it. A club that also appears on the
        # selected side is a real club whatever the search made of it.
        if c.get("is_query_row") and not r["in_selected"]:
            r["is_query_row"] = True
            r["guess_name"] = c.get("guess_name")
        r["confidence"] = c.get("confidence") or r["confidence"]
        r["first_at"] = _earlier(r["first_at"], c.get("first_at"))
        r["last_at"] = _later(r["last_at"], c.get("last_at"))

    for r in rows.values():
        r["source"] = ("both" if r["in_selected"] and r["in_searched"]
                       else "selected" if r["in_selected"] else "searched")
    return list(rows.values())


# ── match a wizard club to its Club Directory row ────────────────────────────

async def _directory_matches(session: AsyncSession, rows: list[dict]) -> dict[str, MarketingClub]:
    """club_key -> the Club Directory club it is, matched on the wizard's own
    captured CA organisation guid first (the strongest signal — it is the same
    guid the PlayHQ crawler keys the directory on, so a club that spells itself
    two ways still lands on one row) and a case-insensitive name second."""
    # A query row is a search term nobody has resolved to a club, so matching
    # it by name would hand back whatever club happens to be spelled like the
    # fragment someone typed. Left unmatched on purpose.
    rows = [r for r in rows if not r.get("is_query_row")]
    guids = {(r.get("org_id") or "").strip() for r in rows if (r.get("org_id") or "").strip()}
    names = {r["key"] for r in rows if r["key"]}

    by_guid: dict[str, MarketingClub] = {}
    by_name: dict[str, MarketingClub] = {}
    if guids:
        for c in (await session.execute(
            select(MarketingClub).where(MarketingClub.grassroots_guid.in_(guids))
        )).scalars().all():
            by_guid[str(c.grassroots_guid)] = c
    if names:
        for c in (await session.execute(
            select(MarketingClub).where(func.lower(MarketingClub.name).in_(names))
        )).scalars().all():
            # First writer wins — two directory rows with the same name is a
            # merge decision for a person, not something to pick between here.
            by_name.setdefault((c.name or "").strip().lower(), c)

    out: dict[str, MarketingClub] = {}
    for r in rows:
        guid = (r.get("org_id") or "").strip()
        club = by_guid.get(guid) if guid else None
        if club is None:
            club = by_name.get(r["key"])
        if club is not None:
            out[r["key"]] = club
    return out


async def _contact_counts(session: AsyncSession, club_ids: list) -> dict:
    """marketing_club_id -> {contacts, emailable} where `emailable` is what a
    list export would actually add: a subscribed contact with a valid email,
    named or not."""
    if not club_ids:
        return {}
    rows = (await session.execute(
        select(MarketingClubContact.marketing_club_id,
               MarketingClubContact.full_name,
               MarketingClubContact.email,
               MarketingClubContact.subscribed)
        .where(MarketingClubContact.marketing_club_id.in_(club_ids))
    )).all()
    out: dict = {}
    seen_emails: dict = {}
    for club_id, full_name, email, subscribed in rows:
        d = out.setdefault(club_id, {"contacts": 0, "emailable": 0, "named": 0, "generic": 0})
        d["contacts"] += 1
        e = norm_email(email)
        if not e or not subscribed:
            continue
        if e in seen_emails.setdefault(club_id, set()):
            continue
        seen_emails[club_id].add(e)
        d["emailable"] += 1
        if (full_name or "").strip():
            d["named"] += 1
        else:
            d["generic"] += 1
    return out


# ── who has been emailed ─────────────────────────────────────────────────────

_EMAIL_HISTORY_SQL = """
    SELECT cc.marketing_club_id                                        AS club_id,
           camp.id::text                                               AS campaign_id,
           COALESCE(NULLIF(TRIM(camp.name), ''), NULLIF(TRIM(camp.subject), ''),
                    'Untitled email')                                  AS campaign_name,
           MAX(r.sent_at)                                              AS sent_at,
           COUNT(*)                                                    AS recipients
    FROM comms_recipients r
    JOIN comms_campaigns camp ON camp.id = r.campaign_id
    JOIN comms_contacts  cc   ON cc.id   = r.contact_id
    WHERE r.status = 'sent'
      AND cc.marketing_club_id IS NOT NULL
      AND camp.audience->>'list_id' IN (SELECT DISTINCT list_id::text FROM wizard_club_lists)
    GROUP BY 1, 2, 3
    ORDER BY MAX(r.sent_at) DESC
"""


async def _email_history(session: AsyncSession) -> dict:
    """marketing_club_id -> [{campaign_id, campaign_name, sent_at, recipients}],
    newest first.

    Derived from the send audit rather than stored: only campaigns whose
    audience was one of the lists THIS page created count, so an unrelated
    club-side send can never read as outreach, and correcting a send (or
    re-sending) needs nothing kept in step here. The list_id comparison is
    made as text on purpose — a campaign's audience JSON is free-form and a
    non-uuid value there would abort a ``::uuid`` cast for every row."""
    out: dict = {}
    for row in (await session.execute(text(_EMAIL_HISTORY_SQL))).mappings().all():
        out.setdefault(row["club_id"], []).append({
            "campaign_id": row["campaign_id"],
            "campaign_name": row["campaign_name"],
            "sent_at": _iso(row["sent_at"]),
            "recipients": int(row["recipients"] or 0),
        })
    return out


async def _exports_by_key(session: AsyncSession) -> dict:
    """club_key -> the lists it has been exported into, newest first. A list a
    super admin has since deleted still shows (``deleted: true``) — the export
    happened, and its campaigns still count towards the club's email history."""
    rows = (await session.execute(
        select(WizardClubList, CommsList.id.label("live_id"))
        .outerjoin(CommsList, CommsList.id == WizardClubList.list_id)
        .order_by(WizardClubList.created_at.desc())
    )).all()
    out: dict = {}
    for w, live_id in rows:
        out.setdefault(w.club_key, []).append({
            "list_id": str(w.list_id),
            "list_name": w.list_name or "",
            "contacts_added": int(w.contacts_added or 0),
            "created_at": _iso(w.created_at),
            "deleted": live_id is None,
        })
    return out


# ── the page payload ─────────────────────────────────────────────────────────

async def list_wizard_clubs(session: AsyncSession, days: int) -> dict:
    """Every club that searched for or selected itself in the wizard, matched to
    the Club Directory, with its contact count and its send history."""
    rows = await merged_wizard_clubs(session, days)
    matches = await _directory_matches(session, rows)
    counts = await _contact_counts(session, [c.id for c in matches.values()])
    history = await _email_history(session)
    exports = await _exports_by_key(session)

    out: list[dict] = []
    for r in rows:
        club = matches.get(r["key"])
        cnt = counts.get(club.id, {}) if club is not None else {}
        emails = history.get(club.id, []) if club is not None else []
        # A club exported before it could be matched to the directory still has
        # its own export rows, so the list history is keyed on the wizard key.
        lists = exports.get(r["key"], [])
        out.append({
            **r,
            "directory": None if club is None else {
                "id": str(club.id),
                "name": club.name,
                "state": club.state or "",
                "association": club.association_name or "",
                "excluded": bool(club.excluded),
                "is_customer": club.existing_org_id is not None,
            },
            "contact_count": int(cnt.get("contacts") or 0),
            "emailable_count": int(cnt.get("emailable") or 0),
            "named_count": int(cnt.get("named") or 0),
            "generic_count": int(cnt.get("generic") or 0),
            "lists": lists,
            "emails": emails,
            "emailed": bool(emails),
            "last_emailed_at": emails[0]["sent_at"] if emails else None,
            "last_campaign_name": emails[0]["campaign_name"] if emails else None,
        })

    out.sort(key=lambda c: (c["last_at"] or ""), reverse=True)
    return {
        "clubs": out,
        "total_clubs": len(out),
        "total_contacts": sum(c["contact_count"] for c in out),
        "total_emailable": sum(c["emailable_count"] for c in out),
        "matched_clubs": sum(1 for c in out if c["directory"]),
        "emailed_clubs": sum(1 for c in out if c["emailed"]),
    }


# ── create a list from a filtered set ────────────────────────────────────────

async def _unique_list_name(session: AsyncSession, org_id, base: str) -> str:
    base = (base or "").strip() or "Wizard clubs"
    existing = set((await session.execute(
        select(CommsList.name).where(CommsList.organisation_id == org_id))).scalars().all())
    if base not in existing:
        return base
    for n in range(2, 1000):
        cand = f"{base} ({n})"
        if cand not in existing:
            return cand
    return f"{base} ({uuid.uuid4().hex[:6]})"


def _club_recipients(club: MarketingClub, contacts: list[MarketingClubContact]) -> list[dict]:
    """Every emailable address the directory holds for one club, deduped.

    A contact with a name is greeted by it; an un-named generic mailbox (and
    the club's own crawled ``contact_email``) is greeted as the committee. An
    opted-out or bounced contact is never included — the directory's own
    suppression is the same gate ``club_directory.export_to_comms`` uses."""
    out: list[dict] = []
    seen: set[str] = set()
    for c in sorted(contacts, key=lambda c: (c.role_rank if c.role_rank is not None else 99,
                                             (c.full_name or "").lower())):
        if not c.subscribed:
            continue
        email = norm_email(c.email)
        if not email or email in seen:
            continue
        seen.add(email)
        full = (c.full_name or "").strip()
        out.append({
            "email": email,
            "name": full or None,
            "first_name": _first_name(full) or GENERIC_FIRST_NAME,
            "generic": not full,
            "contact": c,
        })
    # The club's own mailbox, when the crawl found one no officer row carries.
    club_email = norm_email(getattr(club, "contact_email", None))
    if club_email and club_email not in seen:
        seen.add(club_email)
        out.append({"email": club_email, "name": None,
                    "first_name": GENERIC_FIRST_NAME, "generic": True, "contact": None})
    return out


async def create_list_from_clubs(session: AsyncSession, *, name: str, days: int,
                                 club_keys: list[str], created_by=None) -> dict:
    """Create an auto-generated BetterComms list from the chosen wizard clubs,
    holding every Club Directory contact each one has an email for.

    Idempotent per address: a contact already in BetterComms is reused (and
    linked back to its directory club if it wasn't) rather than colliding on
    the (org, email) unique — so re-exporting a club that overlaps an earlier
    list never mints a duplicate person, and never resurrects an opt-out."""
    outreach = await get_outreach_org(session)
    if outreach is None:
        return {"error": "no_outreach_org",
                "detail": "Designate a BetterCricket marketing org in BetterComms first."}

    wanted = {norm_key(k) for k in (club_keys or []) if norm_key(k)}
    if not wanted:
        return {"error": "no_clubs", "detail": "No clubs were selected."}

    rows = [r for r in await merged_wizard_clubs(session, days) if r["key"] in wanted]
    if not rows:
        return {"error": "no_clubs", "detail": "None of those clubs are in the wizard list."}

    matches = await _directory_matches(session, rows)

    # Every directory contact for the matched clubs, in one query.
    club_ids = [c.id for c in matches.values()]
    contacts_by_club: dict = {}
    if club_ids:
        for c in (await session.execute(
            select(MarketingClubContact)
            .where(MarketingClubContact.marketing_club_id.in_(club_ids))
        )).scalars().all():
            contacts_by_club.setdefault(c.marketing_club_id, []).append(c)

    final_name = await _unique_list_name(session, outreach.id, name)
    lst = CommsList(organisation_id=outreach.id, name=final_name,
                    source="auto", origin=ORIGIN_LABEL)
    session.add(lst)
    await session.flush()  # need lst.id for the membership rows

    existing = {c.email: c for c in (await session.execute(
        select(CommsContact).where(CommsContact.organisation_id == outreach.id))).scalars().all()}

    member_ids: set[uuid.UUID] = set()
    created = 0
    now = func.now()
    per_club: list[dict] = []
    unmatched: list[str] = []
    excluded: list[str] = []

    for r in rows:
        club = matches.get(r["key"])
        if club is None:
            unmatched.append(r["name"])
            continue
        # The one hard guard the Club Directory export also applies: a club a
        # super admin excluded is never contacted, however it was selected.
        if club.excluded:
            excluded.append(r["name"])
            continue

        added_here = 0
        for rec in _club_recipients(club, contacts_by_club.get(club.id, [])):
            c = existing.get(rec["email"])
            if c is None:
                c = CommsContact(
                    organisation_id=outreach.id, email=rec["email"], name=rec["name"],
                    source="import", marketing_club_id=club.id,
                    merge_vars={"first_name": rec["first_name"]},
                    tags=[club.name],
                )
                session.add(c)
                await session.flush()
                existing[rec["email"]] = c
                created += 1
            else:
                # Fill gaps only — never clobber a name someone corrected, and
                # never touch `subscribed` (an opt-out stays an opt-out).
                if rec["name"] and not c.name:
                    c.name = rec["name"]
                if not c.marketing_club_id:
                    c.marketing_club_id = club.id
                mv = dict(c.merge_vars or {})
                if not (mv.get("first_name") or "").strip():
                    mv["first_name"] = rec["first_name"]
                    c.merge_vars = mv
            if rec["contact"] is not None and rec["contact"].exported_at is None:
                rec["contact"].exported_at = now
            if c.id not in member_ids:
                member_ids.add(c.id)
                added_here += 1

        session.add(WizardClubList(
            list_id=lst.id, list_name=final_name, club_key=r["key"], club_name=r["name"],
            marketing_club_id=club.id, contacts_added=added_here, created_by=created_by,
        ))
        per_club.append({"club": r["name"], "contacts": added_here})

    for cid in member_ids:
        session.add(CommsListMember(list_id=lst.id, contact_id=cid))

    await session.commit()
    result = {
        "list_id": str(lst.id),
        "name": final_name,
        "clubs": len(per_club),
        "added": len(member_ids),
        "created_contacts": created,
        "per_club": per_club,
        "unmatched": unmatched,
        "excluded": excluded,
    }
    logger.info("wizard_club_lists.create_list_from_clubs: %s", result)
    return result
