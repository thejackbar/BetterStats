"""Player Cards challenges: sets with a goal and a reward, in the manner of a squad building challenge.

Two kinds, both published by a club's admin to every player:

* EXCHANGE: hand in cards that meet the rules and they are spent. "11 Common cards", "11 Rare cards", "a squad of 11 rated 70 or more",
  "3 Epic cards and 8 Rare". The rules are a small fixed vocabulary (below), checked by one pure function (`evaluate`) that the screen
  asks as the player builds their squad and that the submit asks again under lock, so what the screen says is what the server does.
* COLLECTION: hold a list of cards and keep them ("the 2023 A Grade premiers", "every Legendary"). The list is worked out when the
  admin makes the challenge (from a premiership, a group of players, a tier or a kind of special card) and then fixed.

Completing either pays a reward pack (`reward`: a quality, a size, how many) once per run. The code-defined sets (`player_card_sets`)
pay one too, once per player per set. A player can also keep their own PRIVATE sets: a list of cards they have chosen to collect,
which pay nothing (a player who could make their own rewards would make an easy one) and which nobody else can see.

What is spent. A card handed into an exchange challenge is a `player_card_copies` row and the row is deleted; the run keeps a record
of what was spent. A starting card (source `gift`) is never spent, for the same reason it is never taken back by a trim: it is
re-gifted by the special-card refresh, which would make it free. A player's own card has no row and cannot be spent.
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import date
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import player_card_pack_kinds as kinds, player_card_sets as sets_mod, player_card_swaps as swaps, player_cards as cards

logger = logging.getLogger(__name__)

KINDS = ("exchange", "collection")
TIER_KEYS = ("common", "rare", "epic", "legendary", "special")
TIER_NAME = {"common": "Common", "rare": "Rare", "epic": "Epic", "legendary": "Legendary", "special": "Special"}
KIND_FILTERS = ("any", "players", "specials")
MAX_COUNT = 30
MAX_TITLE = 60
MAX_BLURB = 240
MAX_COMPLETIONS = 50
MAX_CHALLENGES = 40
MAX_KEYS = 200
MAX_MY_SETS = 20
MAX_REWARD_QTY = 5


class ChallengeError(Exception):
    """A refusal the person can read. `status` is the HTTP code the route answers with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


# ── The rules ─────────────────────────────────────────────────────────────────

def _int(v, lo: int, hi: int, what: str) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
        raise ChallengeError(f"{what} must be a whole number.")
    v = int(v)
    if not lo <= v <= hi:
        raise ChallengeError(f"{what} must be from {lo} to {hi}.")
    return v


def clean_rules(raw: Any) -> dict:
    """The rules of an exchange challenge, checked, with defaults filled in. Anything unknown is refused rather than ignored, so a
    typo cannot make a challenge easier than the admin meant."""
    if not isinstance(raw, dict):
        raise ChallengeError("The rules could not be read.")
    allowed = {"count", "kinds", "tiers_only", "min_tier", "min_rating", "max_per_player", "special_kinds", "players", "players_label"}
    extra = set(raw) - allowed
    if extra:
        raise ChallengeError(f"Not a rule we know: {', '.join(sorted(extra))}.")
    out: dict[str, Any] = {"count": _int(raw.get("count", 11), 1, MAX_COUNT, "The number of cards")}
    kind = raw.get("kinds", "any")
    if kind not in KIND_FILTERS:
        raise ChallengeError("Cards can be players, special cards or any.")
    out["kinds"] = kind
    if raw.get("tiers_only"):
        tiers = raw["tiers_only"]
        if not isinstance(tiers, list) or not tiers or any(t not in TIER_KEYS for t in tiers):
            raise ChallengeError("Pick tiers from Common, Rare, Epic, Legendary and Special.")
        out["tiers_only"] = [t for t in TIER_KEYS if t in tiers]
    if raw.get("min_tier"):
        mt = raw["min_tier"]
        if not isinstance(mt, dict) or any(t not in TIER_KEYS for t in mt):
            raise ChallengeError("The minimum per tier could not be read.")
        clean = {t: _int(n, 1, out["count"], f"The number of {TIER_NAME[t]} cards") for t, n in mt.items() if n}
        if sum(clean.values()) > out["count"]:
            raise ChallengeError("The minimums add up to more cards than the challenge takes.")
        if clean:
            out["min_tier"] = clean
    if raw.get("min_rating"):
        out["min_rating"] = _int(raw["min_rating"], 1, 99, "The squad rating")
    if raw.get("max_per_player"):
        out["max_per_player"] = _int(raw["max_per_player"], 1, out["count"], "Cards of one player")
    if raw.get("special_kinds"):
        sk = raw["special_kinds"]
        if not isinstance(sk, list) or any(k not in cards.SPECIAL_KINDS for k in sk):
            raise ChallengeError("That is not a kind of special card.")
        out["special_kinds"] = sorted(set(sk))
    if raw.get("players"):
        ids = raw["players"]
        if not isinstance(ids, list) or len(ids) > MAX_KEYS:
            raise ChallengeError("The list of players could not be read.")
        try:
            out["players"] = sorted({str(uuid.UUID(str(i))) for i in ids})
        except ValueError:
            raise ChallengeError("The list of players could not be read.")
        label = " ".join(str(raw.get("players_label") or "").split())[:80]
        if label:
            out["players_label"] = label
    if "tiers_only" in out:
        for t in out.get("min_tier", {}):
            if t not in out["tiers_only"]:
                raise ChallengeError(f"{TIER_NAME[t]} cards are asked for but the tiers allowed leave them out.")
    return out


def describe_rules(rules: dict) -> list[str]:
    """The rules as short lines for the screen."""
    out = [f"{rules['count']} {'card' if rules['count'] == 1 else 'cards'}"]
    if rules.get("kinds") == "players":
        out.append("Player cards only")
    elif rules.get("kinds") == "specials":
        out.append("Special cards only")
    if rules.get("tiers_only"):
        names = [TIER_NAME[t] for t in rules["tiers_only"]]
        out.append(("All " + names[0]) if len(names) == 1 else "All " + ", ".join(names[:-1]) + " or " + names[-1])
    for t, n in (rules.get("min_tier") or {}).items():
        out.append(f"At least {n} {TIER_NAME[t]}")
    if rules.get("min_rating"):
        out.append(f"Squad rating {rules['min_rating']} or more")
    if rules.get("max_per_player"):
        out.append("All different players" if rules["max_per_player"] == 1 else f"No more than {rules['max_per_player']} cards of one player")
    if rules.get("special_kinds"):
        out.append("Special cards: " + ", ".join(cards.SPECIAL_KINDS[k] for k in rules["special_kinds"]))
    if rules.get("players"):
        out.append(rules.get("players_label") or f"Only cards of {len(rules['players'])} named players")
    return out


def clean_reward(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ChallengeError("The reward could not be read.")
    quality = raw.get("quality", "special")
    if quality not in kinds.QUALITIES:
        raise ChallengeError("Pick one of the pack qualities for the reward.")
    out = {
        "quality": quality,
        "qty": _int(raw.get("qty", 1), 1, MAX_REWARD_QTY, "The number of reward packs"),
        "size": _int(raw.get("size", cards.PACK_SIZE), cards.MIN_PACK_SIZE, cards.MAX_PACK_SIZE, "The cards in a reward pack"),
    }
    title = " ".join(str(raw.get("title") or "").split())[:40]
    if title:
        out["title"] = title
    return out


def evaluate(rules: dict, chosen: list[dict]) -> dict:
    """Do these cards meet the rules? `chosen` is one card payload per card handed in (a card held twice and handed in twice is two
    entries). Pure. Returns `{ok, checks: [{id, label, ok, have, need}], rating}`; every rule gets a line so the screen can show
    what is still missing."""
    n = len(chosen)
    checks: list[dict] = []

    def add(cid: str, label: str, ok: bool, have, need):
        checks.append({"id": cid, "label": label, "ok": bool(ok), "have": have, "need": need})

    add("count", f"{rules['count']} {'card' if rules['count'] == 1 else 'cards'}", n == rules["count"], n, rules["count"])
    if rules.get("kinds") in ("players", "specials"):
        want = "player" if rules["kinds"] == "players" else "special"
        wrong = sum(1 for c in chosen if c["kind"] != want)
        add("kinds", "Player cards only" if want == "player" else "Special cards only", wrong == 0, n - wrong, n)
    if rules.get("tiers_only"):
        wrong = sum(1 for c in chosen if c["tier"] not in rules["tiers_only"])
        names = [TIER_NAME[t] for t in rules["tiers_only"]]
        add("tiers_only", ("All " + names[0]) if len(names) == 1 else "All " + ", ".join(names[:-1]) + " or " + names[-1], wrong == 0, n - wrong, n)
    for t, need in (rules.get("min_tier") or {}).items():
        have = sum(1 for c in chosen if c["tier"] == t)
        add(f"min_tier:{t}", f"At least {need} {TIER_NAME[t]}", have >= need, have, need)
    players = [c for c in chosen if c["kind"] == "player" and c.get("rarity")]
    rating = round(sum(c["rarity"] for c in players) / len(players), 1) if players else None
    if rules.get("min_rating"):
        add("min_rating", f"Squad rating {rules['min_rating']} or more", rating is not None and rating >= rules["min_rating"], rating or 0, rules["min_rating"])
    if rules.get("max_per_player"):
        per: dict[str, int] = {}
        for c in chosen:
            per[c["player_id"]] = per.get(c["player_id"], 0) + 1
        most = max(per.values(), default=0)
        cap = rules["max_per_player"]
        add("max_per_player", "All different players" if cap == 1 else f"No more than {cap} cards of one player", most <= cap, most, cap)
    if rules.get("special_kinds"):
        wrong = sum(1 for c in chosen if c["kind"] == "special" and c.get("special_kind") not in rules["special_kinds"])
        add("special_kinds", "Special cards: " + ", ".join(cards.SPECIAL_KINDS[k] for k in rules["special_kinds"]), wrong == 0, n - wrong, n)
    if rules.get("players"):
        allowed = set(rules["players"])
        wrong = sum(1 for c in chosen if c["player_id"] not in allowed)
        add("players", rules.get("players_label") or "Only the named players", wrong == 0, n - wrong, n)
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "rating": rating}


# ── Choosing cards: selectors ────────────────────────────────────────────────────

SELECTOR_TYPES = ("players", "premiership", "tier", "special_kind")


async def premiership_options(db: AsyncSession, club: Organisation, snap: dict) -> list[dict]:
    """Every premiership the club has recorded, one entry per season and grade, with how many of its players have a card."""
    rows = (await db.execute(text("""
        SELECT COALESCE(season, '') AS season, COALESCE(subcategory, '') AS grade, ARRAY_AGG(DISTINCT player_id::text) AS pids
          FROM player_achievements
         WHERE org_id = CAST(:o AS UUID) AND category = 'Premiership' AND player_id IS NOT NULL
         GROUP BY 1, 2 ORDER BY 1 DESC, 2
    """), {"o": str(club.id)})).mappings().all()
    drawable = {pid for pid, f in snap["figs"].items() if f["matches"] > 0 and pid in snap["people"]}
    out = []
    for r in rows:
        n = len([p for p in r["pids"] if p in drawable])
        if n:
            out.append({"season": r["season"], "grade": r["grade"], "players": n,
                        "label": f"{r['season'] or 'Premiers'}{(' ' + r['grade']) if r['grade'] else ''} premiers".strip()})
    return out


async def resolve_selector(db: AsyncSession, club: Organisation, snap: dict, raw: Any) -> tuple[dict, list[str], str]:
    """A selector as the screen sends it, to `(clean selector, card keys, a name it suggests)`. The keys are fixed at this moment:
    a set is the cards that met the description when it was made."""
    if not isinstance(raw, dict) or raw.get("type") not in SELECTOR_TYPES:
        raise ChallengeError("Pick what to collect.")
    drawable = [pid for pid, f in snap["figs"].items() if f["matches"] > 0 and pid in snap["people"]]
    t = raw["type"]
    if t == "players":
        ids = raw.get("player_ids")
        if not isinstance(ids, list) or not ids:
            raise ChallengeError("Pick at least one player.")
        keep = {str(i) for i in ids}
        keys = [f"p:{pid}" for pid in drawable if pid in keep]
        return {"type": t, "player_ids": sorted(keep)}, keys, "My players"
    if t == "premiership":
        season, grade = str(raw.get("season") or ""), str(raw.get("grade") or "")
        pids = {r[0] for r in (await db.execute(text("""
            SELECT DISTINCT player_id::text FROM player_achievements
             WHERE org_id = CAST(:o AS UUID) AND category = 'Premiership' AND player_id IS NOT NULL
               AND COALESCE(season, '') = :s AND COALESCE(subcategory, '') = :g
        """), {"o": str(club.id), "s": season, "g": grade})).fetchall()}
        keys = [f"p:{pid}" for pid in drawable if pid in pids]
        return {"type": t, "season": season, "grade": grade}, keys, f"{season or 'Premiers'}{(' ' + grade) if grade else ''} premiers".strip()
    if t == "tier":
        tier = raw.get("tier")
        if tier not in ("common", "rare", "epic", "legendary"):
            raise ChallengeError("Pick a tier.")
        keys = [f"p:{pid}" for pid in drawable if (snap["rating"].get(pid) or {}).get("tier") == tier]
        return {"type": t, "tier": tier}, keys, f"Every {TIER_NAME[tier]}"
    kind = raw.get("kind")
    if kind not in cards.SPECIAL_KINDS:
        raise ChallengeError("That is not a kind of special card.")
    rows = (await db.execute(text("SELECT id::text, player_id::text FROM player_special_cards WHERE organisation_id = CAST(:o AS UUID) AND kind = :k"),
                             {"o": str(club.id), "k": kind})).fetchall()
    keys = [f"s:{i}" for i, pid in rows if pid in snap["people"]]
    return {"type": t, "kind": kind}, keys, f"Every {cards.SPECIAL_KINDS[kind].lower()}"


def _keys_ok(keys: list[str]) -> list[str]:
    keys = sorted(set(keys))
    if not keys:
        raise ChallengeError("Nobody has a card that matches that yet.")
    if len(keys) > MAX_KEYS:
        raise ChallengeError(f"That is more than {MAX_KEYS} cards. Narrow it down.")
    return keys


# ── Admin: the challenges a club offers ──────────────────────────────────────────

def _row(r) -> dict:
    return {
        "id": str(r["id"]), "kind": r["kind"], "title": r["title"], "blurb": r["blurb"], "rules": r["rules"] or {}, "reward": r["reward"] or {},
        "max_completions": r["max_completions"], "starts_on": r["starts_on"].isoformat() if r["starts_on"] else None,
        "ends_on": r["ends_on"].isoformat() if r["ends_on"] else None, "active": bool(r["active"]), "sort_order": r["sort_order"],
    }


_COLS = "id, kind, title, blurb, rules, reward, max_completions, starts_on, ends_on, active, sort_order"


async def members_view(db, club, snap, keys: list[str], held: set[str]) -> list[dict]:
    """The cards of a collection or a private set, as short lines with whether the player holds each (never more than 60)."""
    keys = list(keys)[:60]
    special_ids = [k[2:] for k in keys if k.startswith("s:")]
    specials = await cards._specials_by_id(db, club.id, special_ids) if special_ids else {}
    out = []
    for k in keys:
        if k.startswith("p:"):
            person = snap["people"].get(k[2:])
            if person:
                out.append({"key": k, "name": person["display_name"], "tier": (snap["rating"].get(k[2:]) or {}).get("tier", "common"), "held": k in held})
        else:
            row = specials.get(k[2:])
            person = snap["people"].get(str(row["player_id"])) if row else None
            if row and person:
                out.append({"key": k, "name": f"{person['display_name']}: {row['title']}", "tier": "special", "held": k in held})
    return out


async def _clean_body(db, club, snap, body: dict) -> dict:
    kind = body.get("kind")
    if kind not in KINDS:
        raise ChallengeError("A challenge is an exchange or a collection.")
    title = " ".join(str(body.get("title") or "").split())[:MAX_TITLE]
    if not title:
        raise ChallengeError("Give the challenge a name.")
    blurb = " ".join(str(body.get("blurb") or "").split())[:MAX_BLURB] or None
    if kind == "exchange":
        raw_rules = dict(body.get("rules") or {})
        side = raw_rules.pop("premiership", None)
        if side:
            # "Only players from this premiership side": turned into the players now, so the rule is a plain list afterwards.
            _sel, keys, label = await resolve_selector(db, club, snap, {"type": "premiership", **(side if isinstance(side, dict) else {})})
            ids = [k[2:] for k in keys if k.startswith("p:")]
            if not ids:
                raise ChallengeError("Nobody from that premiership has a card yet.")
            raw_rules["players"], raw_rules["players_label"] = ids, label
        rules = clean_rules(raw_rules)
        maxc = _int(body.get("max_completions", 1), 1, MAX_COMPLETIONS, "How many times a player can complete it")
    else:
        selector, keys, _name = await resolve_selector(db, club, snap, body.get("selector"))
        keys = _keys_ok(keys)
        need = body.get("need")
        need = len(keys) if not need else _int(need, 1, len(keys), "The number of cards to hold")
        rules = {"selector": selector, "card_keys": keys, "need": need}
        maxc = 1
    starts = body.get("starts_on") or None
    ends = body.get("ends_on") or None
    try:
        starts = date.fromisoformat(starts) if isinstance(starts, str) else starts
        ends = date.fromisoformat(ends) if isinstance(ends, str) else ends
    except ValueError:
        raise ChallengeError("The dates could not be read.")
    if starts and ends and ends < starts:
        raise ChallengeError("The last day cannot be before the first.")
    return {"kind": kind, "title": title, "blurb": blurb, "rules": rules, "reward": clean_reward(body.get("reward") or {}),
            "max_completions": maxc, "starts_on": starts, "ends_on": ends, "active": body.get("active") is not False,
            "sort_order": _int(body.get("sort_order", 0), 0, 1000, "The order")}


async def admin_list(db: AsyncSession, club: Organisation) -> list[dict]:
    rows = (await db.execute(text(f"SELECT {_COLS} FROM club_card_challenges WHERE organisation_id = CAST(:o AS UUID) ORDER BY sort_order, created_at"),
                             {"o": str(club.id)})).mappings().all()
    done = {r[0]: (r[1], r[2]) for r in (await db.execute(text(
        "SELECT challenge_key, COUNT(*), COUNT(DISTINCT player_id) FROM player_card_challenge_runs WHERE organisation_id = CAST(:o AS UUID) GROUP BY 1"),
        {"o": str(club.id)})).fetchall()}
    out = []
    for r in rows:
        d = _row(r)
        runs, players = done.get(d["id"], (0, 0))
        d["completions"], d["players_done"] = int(runs), int(players)
        d["requirements"] = describe_rules(d["rules"]) if d["kind"] == "exchange" else [f"Hold {d['rules'].get('need')} of {len(d['rules'].get('card_keys', []))} cards"]
        out.append(d)
    return out


async def admin_save(db: AsyncSession, club: Organisation, snap: dict, body: dict, challenge_id: Optional[str], by: Optional[str]) -> dict:
    data = await _clean_body(db, club, snap, body)
    params = {"o": str(club.id), "kind": data["kind"], "title": data["title"], "blurb": data["blurb"], "rules": json.dumps(data["rules"]),
              "reward": json.dumps(data["reward"]), "maxc": data["max_completions"], "s": data["starts_on"], "e": data["ends_on"],
              "active": data["active"], "order": data["sort_order"]}
    if challenge_id:
        res = await db.execute(text("""
            UPDATE club_card_challenges SET kind = :kind, title = :title, blurb = :blurb, rules = CAST(:rules AS JSONB), reward = CAST(:reward AS JSONB),
                   max_completions = :maxc, starts_on = :s, ends_on = :e, active = :active, sort_order = :order, updated_at = NOW()
             WHERE id = CAST(:id AS UUID) AND organisation_id = CAST(:o AS UUID)
        """), {**params, "id": challenge_id})
        if not res.rowcount:
            raise ChallengeError("Challenge not found.", 404)
        new_id = challenge_id
    else:
        n = (await db.execute(text("SELECT COUNT(*) FROM club_card_challenges WHERE organisation_id = CAST(:o AS UUID)"), {"o": str(club.id)})).scalar()
        if int(n or 0) >= MAX_CHALLENGES:
            raise ChallengeError(f"A club can have {MAX_CHALLENGES} challenges. Remove an old one first.")
        new_id = (await db.execute(text("""
            INSERT INTO club_card_challenges (organisation_id, kind, title, blurb, rules, reward, max_completions, starts_on, ends_on, active, sort_order, created_by)
            VALUES (CAST(:o AS UUID), :kind, :title, :blurb, CAST(:rules AS JSONB), CAST(:reward AS JSONB), :maxc, :s, :e, :active, :order, :by) RETURNING id::text
        """), {**params, "by": by})).scalar()
    return {"id": new_id, **{k: data[k] for k in ("kind", "title")}}


async def admin_delete(db: AsyncSession, club: Organisation, challenge_id: str) -> bool:
    """Remove a challenge. What players completed stays on record (and the packs they earned stay theirs)."""
    res = await db.execute(text("DELETE FROM club_card_challenges WHERE id = CAST(:id AS UUID) AND organisation_id = CAST(:o AS UUID)"),
                           {"id": challenge_id, "o": str(club.id)})
    return bool(res.rowcount)


# ── What a player sees ────────────────────────────────────────────────────────────

async def _held(db, club, me: str) -> tuple[dict, dict]:
    """`(held, spendable)`: copies held per card, and the copies of each that could be spent (a starting card never can)."""
    held = (await swaps._rows_by_card(db, club.id, me)).get(me, {})
    rows = (await db.execute(text("""
        SELECT subject_player_id::text, special_id::text, COUNT(*) FROM player_card_copies
         WHERE organisation_id = CAST(:o AS UUID) AND owner_player_id = CAST(:me AS UUID) AND source <> 'gift'
         GROUP BY 1, 2
    """), {"o": str(club.id), "me": me})).fetchall()
    spend = {(s, sp): int(n) for s, sp, n in rows}
    return held, spend


def _window(ch: dict, today: date) -> str:
    if ch["starts_on"] and today < date.fromisoformat(ch["starts_on"]):
        return "soon"
    if ch["ends_on"] and today > date.fromisoformat(ch["ends_on"]):
        return "ended"
    return "open"


async def _runs(db, club, me: str) -> dict[str, int]:
    rows = (await db.execute(text("SELECT challenge_key, COUNT(*) FROM player_card_challenge_runs WHERE player_id = CAST(:me AS UUID) GROUP BY 1"),
                             {"me": me})).fetchall()
    return {k: int(n) for k, n in rows}


def reward_view(reward: dict, fallback_title: str) -> dict:
    q = kinds.QUALITIES.get(reward.get("quality") or "special") or kinds.QUALITIES["special"]
    return {"quality": reward.get("quality", "special"), "quality_label": q.label, "qty": reward.get("qty", 1), "size": reward.get("size", cards.PACK_SIZE),
            "title": reward.get("title") or fallback_title}


async def _grant(db, org: str, me: str, key: str, n: int, title: str, reward: dict) -> int:
    made = 0
    for i in range(1, int(reward.get("qty", 1)) + 1):
        res = await db.execute(text("""
            INSERT INTO player_card_packs (organisation_id, player_id, source, ref_key, label, quality, size)
            VALUES (CAST(:o AS UUID), CAST(:me AS UUID), 'reward', :ref, :label, :q, CAST(:size AS INT))
            ON CONFLICT (player_id, source, ref_key) DO NOTHING
        """), {"o": org, "me": me, "ref": f"{key}:{n}:{i}", "label": reward.get("title") or title, "q": reward.get("quality", "special"),
               "size": reward.get("size", cards.PACK_SIZE)})
        made += res.rowcount or 0
    return made


async def _record_run(db, org: str, me: str, key: str, title: str, n: int, submitted: list) -> bool:
    res = await db.execute(text("""
        INSERT INTO player_card_challenge_runs (organisation_id, challenge_key, player_id, title, n, submitted)
        VALUES (CAST(:o AS UUID), :k, CAST(:me AS UUID), :t, :n, CAST(:s AS JSONB))
        ON CONFLICT (player_id, challenge_key, n) DO NOTHING
    """), {"o": org, "k": key, "me": me, "t": title, "n": n, "s": json.dumps(submitted)})
    return bool(res.rowcount)


def set_reward(total: int) -> dict:
    """What a code-defined set pays: a bigger set pays better, one pack."""
    quality = "premium" if total >= 15 else "special" if total >= 6 else "boosted"
    return {"quality": quality, "qty": 1, "size": cards.PACK_SIZE}


async def claim_rewards(db: AsyncSession, club: Organisation, snap: dict, me: str) -> list[dict]:
    """Pay what this player has earned and not yet been paid for: every complete code-defined set, and every complete collection a
    club published. Add-only and once each, so calling it on every visit is safe. Returns the rewards just paid, for a message."""
    org = str(club.id)
    paid: list[dict] = []
    held = await sets_mod.held_keys(db, club, me)
    for d in await sets_mod.definitions(db, club, snap):
        keys = sets_mod.card_keys(d)
        if keys and keys <= held:
            reward = set_reward(len(keys))
            if await _record_run(db, org, me, f"set:{d['key']}", d["title"], 1, []):
                await _grant(db, org, me, f"set:{d['key']}", 1, d["title"], reward)
                paid.append({"title": d["title"], **reward_view(reward, d["title"])})
    today = cards.club_today(snap["settings"])
    for ch in await admin_list(db, club):
        if ch["kind"] != "collection" or not ch["active"] or _window(ch, today) != "open":
            continue
        keys = set(ch["rules"].get("card_keys") or [])
        need = ch["rules"].get("need") or len(keys)
        if keys and len(keys & held) >= need:
            if await _record_run(db, org, me, ch["id"], ch["title"], 1, []):
                await _grant(db, org, me, ch["id"], 1, ch["title"], ch["reward"])
                paid.append({"title": ch["title"], **reward_view(ch["reward"], ch["title"])})
    return paid


async def _my_sets(db, club, snap, me: str, held: set[str]) -> list[dict]:
    rows = (await db.execute(text("SELECT id::text, title, selector, card_keys, created_at FROM player_card_my_sets WHERE player_id = CAST(:me AS UUID) ORDER BY created_at"),
                             {"me": me})).mappings().all()
    out = []
    for r in rows:
        keys = [k for k in (r["card_keys"] or [])]
        owned = len(set(keys) & held)
        out.append({"id": r["id"], "title": r["title"], "selector": r["selector"], "total": len(keys), "owned": owned,
                    "percent": round(100 * owned / len(keys)) if keys else 0, "complete": bool(keys) and owned >= len(keys),
                    "members": await members_view(db, club, snap, keys, held)})
    return out


async def overview(db: AsyncSession, club: Organisation, snap: dict, me: str) -> dict:
    """The challenges a player can see, how far they are, and their own private sets."""
    held_cards, spend = await _held(db, club, me)
    held = {swaps.key_of(*c) for c, n in held_cards.items() if n > 0} | {f"p:{me}"}
    runs = await _runs(db, club, me)
    today = cards.club_today(snap["settings"])
    out = []
    for ch in await admin_list(db, club):
        if not ch["active"]:
            continue
        status = _window(ch, today)
        done = runs.get(ch["id"], 0)
        row = {"id": ch["id"], "kind": ch["kind"], "title": ch["title"], "blurb": ch["blurb"], "reward": reward_view(ch["reward"], ch["title"]),
               "starts_on": ch["starts_on"], "ends_on": ch["ends_on"], "status": status, "completions": done, "max_completions": ch["max_completions"],
               "finished": done >= ch["max_completions"]}
        if ch["kind"] == "exchange":
            row["requirements"] = describe_rules(ch["rules"])
            row["count"] = ch["rules"]["count"]
        else:
            keys = set(ch["rules"].get("card_keys") or [])
            need = ch["rules"].get("need") or len(keys)
            owned = len(keys & held)
            row.update({"total": len(keys), "need": need, "owned": min(owned, len(keys)), "percent": round(100 * min(owned, need) / need) if need else 0,
                        "complete": owned >= need, "members": await members_view(db, club, snap, sorted(keys), held)})
        out.append(row)
    return {"challenges": out, "my_sets": await _my_sets(db, club, snap, me, held), "max_my_sets": MAX_MY_SETS}


async def _load(db, club, challenge_id: str) -> dict:
    try:
        uuid.UUID(str(challenge_id))
    except ValueError:
        raise ChallengeError("Challenge not found.", 404)
    r = (await db.execute(text(f"SELECT {_COLS} FROM club_card_challenges WHERE id = CAST(:id AS UUID) AND organisation_id = CAST(:o AS UUID)"),
                          {"id": challenge_id, "o": str(club.id)})).mappings().first()
    if not r or not r["active"]:
        raise ChallengeError("Challenge not found.", 404)
    return _row(r)


async def detail(db: AsyncSession, club: Organisation, snap: dict, me: str, challenge_id: str) -> dict:
    """One exchange challenge with the cards the player can spend on it."""
    ch = await _load(db, club, challenge_id)
    if ch["kind"] != "exchange":
        raise ChallengeError("That challenge is not an exchange.", 409)
    held, spend = await _held(db, club, me)
    specials = await swaps._special_subjects(db, club.id, [c[1] for c in spend if c[1]])
    pool = []
    for card, n in spend.items():
        payload = swaps._payload(snap, card, specials)
        if payload and n > 0:
            pool.append({**payload, "spendable": n})
    order = {"special": 0, "legendary": 1, "epic": 2, "rare": 3, "common": 4}
    pool.sort(key=lambda c: (order.get(c["tier"], 5), -(c.get("rarity") or 0), c["name"]))
    runs = await _runs(db, club, me)
    return {"id": ch["id"], "title": ch["title"], "blurb": ch["blurb"], "rules": ch["rules"], "requirements": describe_rules(ch["rules"]),
            "reward": reward_view(ch["reward"], ch["title"]), "status": _window(ch, cards.club_today(snap["settings"])),
            "completions": runs.get(ch["id"], 0), "max_completions": ch["max_completions"], "cards": pool}


async def _expand(db, club, snap, me: str, selection: Any, spend: dict) -> tuple[list[dict], dict[tuple, int]]:
    """A selection `[{key, qty}]` as one payload per card, and the copies wanted of each. Refuses cards the player cannot spend."""
    if not isinstance(selection, list) or len(selection) > 200:
        raise ChallengeError("The cards could not be read.")
    want: dict[tuple, int] = {}
    for item in selection:
        if not isinstance(item, dict):
            raise ChallengeError("The cards could not be read.")
        try:
            card, _payload = await swaps._resolve(db, club.id, snap, str(item.get("key") or ""))
        except swaps.SwapError as exc:
            raise ChallengeError(exc.message, exc.status)
        qty = _int(item.get("qty", 1), 1, 99, "How many of a card")
        want[card] = want.get(card, 0) + qty
    specials = await swaps._special_subjects(db, club.id, [c[1] for c in want if c[1]])
    chosen: list[dict] = []
    for card, qty in want.items():
        if spend.get(card, 0) < qty:
            raise ChallengeError("You can only hand in cards you hold, and not your own card or a starting card.")
        payload = swaps._payload(snap, card, specials)
        if payload is None:
            raise ChallengeError("That card is not available.", 409)
        chosen.extend([payload] * qty)
    return chosen, want


async def check(db: AsyncSession, club: Organisation, snap: dict, me: str, challenge_id: str, selection: Any) -> dict:
    ch = await _load(db, club, challenge_id)
    if ch["kind"] != "exchange":
        raise ChallengeError("That challenge is not an exchange.", 409)
    _held_cards, spend = await _held(db, club, me)
    chosen, _want = await _expand(db, club, snap, me, selection, spend)
    return evaluate(ch["rules"], chosen)


async def submit(db: AsyncSession, club: Organisation, snap: dict, me: str, challenge_id: str, selection: Any) -> dict:
    """Hand the cards in: check the rules, spend the cards, record the run, pay the reward. All or nothing; the caller commits."""
    ch = await _load(db, club, challenge_id)
    if ch["kind"] != "exchange":
        raise ChallengeError("That challenge is not an exchange.", 409)
    status = _window(ch, cards.club_today(snap["settings"]))
    if status != "open":
        raise ChallengeError("That challenge is not open." if status == "ended" else "That challenge has not started.", 409)
    org = str(club.id)
    # One submit at a time per player, so two taps cannot spend the same cards or pay twice.
    await db.execute(text("SELECT id FROM players WHERE id = CAST(:me AS UUID) FOR UPDATE"), {"me": me})
    done = (await _runs(db, club, me)).get(ch["id"], 0)
    if done >= ch["max_completions"]:
        raise ChallengeError("You have already completed that challenge.", 409)
    _held_cards, spend = await _held(db, club, me)
    chosen, want = await _expand(db, club, snap, me, selection, spend)
    verdict = evaluate(ch["rules"], chosen)
    if not verdict["ok"]:
        raise ChallengeError("Those cards do not meet the challenge yet.", 422)
    spent: list[dict] = []
    for card, qty in want.items():
        ids = [r[0] for r in (await db.execute(text("""
            SELECT id::text FROM player_card_copies
             WHERE organisation_id = CAST(:o AS UUID) AND owner_player_id = CAST(:me AS UUID) AND subject_player_id = CAST(:s AS UUID)
               AND special_id IS NOT DISTINCT FROM CAST(:sp AS UUID) AND source <> 'gift'
             ORDER BY obtained_at ASC, id FOR UPDATE
        """), {"o": org, "me": me, "s": card[0], "sp": card[1]})).fetchall()][:qty]
        if len(ids) < qty:
            raise ChallengeError("You no longer hold all of those cards.", 409)
        await db.execute(text("DELETE FROM player_card_copies WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids})
        spent.append({"key": swaps.key_of(*card), "qty": qty})
    n = done + 1
    if not await _record_run(db, org, me, ch["id"], ch["title"], n, spent):
        raise ChallengeError("You have already completed that challenge.", 409)
    packs = await _grant(db, org, me, ch["id"], n, ch["title"], ch["reward"])
    return {"ok": True, "spent": sum(s["qty"] for s in spent), "packs": packs, "reward": reward_view(ch["reward"], ch["title"]),
            "completions": n, "max_completions": ch["max_completions"]}


# ── A player's own sets ────────────────────────────────────────────────────────────

async def create_my_set(db: AsyncSession, club: Organisation, snap: dict, me: str, body: dict) -> dict:
    n = (await db.execute(text("SELECT COUNT(*) FROM player_card_my_sets WHERE player_id = CAST(:me AS UUID)"), {"me": me})).scalar()
    if int(n or 0) >= MAX_MY_SETS:
        raise ChallengeError(f"You can keep {MAX_MY_SETS} sets. Delete one to make another.")
    selector, keys, suggested = await resolve_selector(db, club, snap, body.get("selector"))
    keys = _keys_ok(keys)
    title = " ".join(str(body.get("title") or "").split())[:MAX_TITLE] or suggested
    new_id = (await db.execute(text("""
        INSERT INTO player_card_my_sets (organisation_id, player_id, title, selector, card_keys)
        VALUES (CAST(:o AS UUID), CAST(:me AS UUID), :t, CAST(:sel AS JSONB), CAST(:keys AS JSONB)) RETURNING id::text
    """), {"o": str(club.id), "me": me, "t": title, "sel": json.dumps(selector), "keys": json.dumps(keys)})).scalar()
    return {"id": new_id, "title": title, "total": len(keys)}


async def delete_my_set(db: AsyncSession, me: str, set_id: str) -> bool:
    try:
        uuid.UUID(str(set_id))
    except ValueError:
        return False
    res = await db.execute(text("DELETE FROM player_card_my_sets WHERE id = CAST(:id AS UUID) AND player_id = CAST(:me AS UUID)"), {"id": set_id, "me": me})
    return bool(res.rowcount)
