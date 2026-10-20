"""A club's own Honour Board order (migration 324).

The standard order lives in services/honours.py (``_GROUP_ORDER``,
``_ROLE_PRIORITY``, most recent term first). A club that wants something else
(Life Members first, Allan Godfrey above everyone, Treasurer before Secretary)
saves a layout, and ``office_bearer_boards`` applies it on read. Nothing about
the honours themselves is stored here: only the order they are listed in.

Stored in ``organisations.honour_board_layout`` as

    {"groups":  ["Life Members", "Executive Committee"],
     "roles":   {"Executive Committee": ["President", "Treasurer", "Secretary"]},
     "holders": {"Life Members": {"Life Membership":
                    {"sort": "oldest", "order": ["id:<player uuid>", "name:jo bloggs"]}}}}

NULL (or anything that cleans down to nothing) means the standard order.

Anything a layout does not mention keeps its standard place AFTER what it does
mention, so a role recorded after the layout was saved is never hidden. Unknown
sort words are dropped (the standard "newest" applies), never guessed at.
"""
from __future__ import annotations

import re
from typing import Any, Optional

SORT_NEWEST = "newest"
SORT_OLDEST = "oldest"
SORT_MANUAL = "manual"
SORT_MODES = (SORT_NEWEST, SORT_OLDEST, SORT_MANUAL)

NAME_MAX_CHARS = 120
KEY_MAX_CHARS = 200
MAX_NAMES = 200
MAX_ORDER = 2000
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def lc(value: Optional[str]) -> str:
    """The case-insensitive form a group or role is matched on."""
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def _name(raw: Any, limit: int = NAME_MAX_CHARS) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    s = re.sub(r"\s+", " ", _CONTROL.sub(" ", raw)).strip()[:limit]
    return s or None


def _names(raw: Any, limit: int = NAME_MAX_CHARS, cap: int = MAX_NAMES,
           fold_case: bool = True) -> list[str]:
    """A tidy, de-duplicated list of names, order kept. Not a list gives []."""
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        n = _name(item, limit)
        if n is None:
            continue
        k = lc(n) if fold_case else n
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
        if len(out) >= cap:
            break
    return out


def clean_layout(raw: Any) -> Optional[dict]:
    """The layout reduced to what ``office_bearer_boards`` understands, or None
    when nothing is left (which stores NULL and means the standard order).

    Idempotent, so it cleans what is stored as well as what is sent, and a
    hand-edited or half-written value can never break the public page.
    """
    if not isinstance(raw, dict):
        return None

    groups = _names(raw.get("groups"))

    roles: dict[str, list[str]] = {}
    raw_roles = raw.get("roles")
    if isinstance(raw_roles, dict):
        for g, lst in raw_roles.items():
            gname = _name(g)
            names = _names(lst)
            if gname and names and lc(gname) not in {lc(k) for k in roles}:
                roles[gname] = names

    holders: dict[str, dict[str, dict]] = {}
    raw_holders = raw.get("holders")
    if isinstance(raw_holders, dict):
        for g, by_role in raw_holders.items():
            gname = _name(g)
            if not gname or not isinstance(by_role, dict):
                continue
            kept: dict[str, dict] = {}
            for r, cfg in by_role.items():
                rname = _name(r)
                if not rname or not isinstance(cfg, dict) or lc(rname) in {lc(k) for k in kept}:
                    continue
                sort = cfg.get("sort")
                sort = sort if sort in SORT_MODES else SORT_NEWEST
                order = _names(cfg.get("order"), KEY_MAX_CHARS, MAX_ORDER, fold_case=False)
                if sort == SORT_NEWEST and not order:
                    continue
                kept[rname] = {"sort": sort, "order": order}
            if kept and lc(gname) not in {lc(k) for k in holders}:
                holders[gname] = kept

    out: dict = {}
    if groups:
        out["groups"] = groups
    if roles:
        out["roles"] = roles
    if holders:
        out["holders"] = holders
    return out or None


def group_rank(layout: Optional[dict]) -> dict[str, int]:
    return {lc(n): i for i, n in enumerate((layout or {}).get("groups") or [])}


def role_rank(layout: Optional[dict], group: str) -> dict[str, int]:
    for g, names in ((layout or {}).get("roles") or {}).items():
        if lc(g) == lc(group):
            return {lc(n): i for i, n in enumerate(names)}
    return {}


def holder_setting(layout: Optional[dict], group: str, role: str) -> tuple[str, dict[str, int]]:
    """How the people under one role are sorted, and the club's own order
    among them (person key -> position)."""
    for g, by_role in ((layout or {}).get("holders") or {}).items():
        if lc(g) != lc(group):
            continue
        for r, cfg in by_role.items():
            if lc(r) == lc(role):
                return cfg.get("sort") or SORT_NEWEST, {k: i for i, k in enumerate(cfg.get("order") or [])}
    return SORT_NEWEST, {}
