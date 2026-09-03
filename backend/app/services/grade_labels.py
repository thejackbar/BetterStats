"""Grade category labels + auto-classification.

A club's grades carry one category from a small fixed set so the public site can
group them (Senior / Junior / Women's ...) and clubs can choose which ones to
share publicly. The label attaches to a grade name club-wide (all seasons), the
same way the display-name override and fee format do. Visibility is a separate
per-grade flag (``grades.is_public``), so a club can hide a whole junior
programme from public view while keeping the label for their own admin.

The category is a *suggestion* until a club admin confirms it — we guess it from
the grade name and let them correct it on /admin/grades. New grades get the guess
persisted on sync so a club is never labelling from scratch; existing grades read
their suggestion on the fly (nothing is written as a guess).
"""
import re

# Canonical category keys stored in grades.category. NULL/absent means the grade
# has not been categorised yet — readers fall back to the name-based suggestion.
GRADE_CATEGORIES = ("senior", "junior", "womens", "masters", "mixed")

CATEGORY_LABELS = {
    # "senior" is the stored key and always has been. It reads as "Men's"
    # because that is what it means in practice once women's, junior and
    # masters cricket each have a key of their own — a club filtering its
    # dashboard is asking for the men's grades, not for "adults". The key is
    # left alone so no stored row has to move.
    "senior": "Men's",
    "junior": "Juniors",
    "womens": "Women's",
    "masters": "Masters",
    "mixed": "Mixed / Other",
}

# The format a grade is played in — a separate axis from the category above.
# A grade is a Men's grade OR a Women's grade; it is separately a T20 grade or
# a two-day grade, and the two answers do not constrain each other.
MATCH_FORMATS = ("two_day", "one_day", "t20")

FORMAT_LABELS = {
    "two_day": "Two Day",
    "one_day": "One Day",
    "t20": "T20",
}

# Age-group / youth markers. Anything with an explicit age or youth programme
# name is a junior grade, regardless of gender, because that is the split clubs
# reach for first ("Girls U14" is a junior team).
#
# The age patterns end `\d+s?` rather than `\d+\b`. A trailing word boundary
# after the number cannot match before a letter, so "Under 14s", "U14s" and
# "Year 9s" — the plural spelling most clubs actually use — read as SENIOR,
# which put junior seasons inside senior career averages and emptied the
# Juniors filter. "Under 14" and "U14" always worked, which is why it went
# unnoticed.
_JUNIOR = re.compile(
    r"\b(?:under[\s-]?\d+s?|u\d+s?|colts?|juniors?|youth|year[\s-]?\d+s?|yr[\s-]?\d+s?"
    r"|milo|blaster|master[\s-]?blaster|kanga|in2cricket|woolworths)\b",
    re.I,
)
_WOMENS = re.compile(
    r"\b(?:women'?s?|woman|ladies|lady|girls?|female|pswl)\b",
    re.I,
)
# Same trailing-`s` rule as _JUNIOR above: "Over 40s" is how a club writes it.
_MASTERS = re.compile(
    r"\b(?:masters?|veterans?|vets?|over[\s-]?\d+s?|super[\s-]?rules|legends)\b",
    re.I,
)
_MIXED = re.compile(
    r"\b(?:mixed|social|all[\s-]?abilities|come[\s-]?and[\s-]?try|come[\s-]?'?n'?[\s-]?try)\b",
    re.I,
)


def normalise_category(value) -> str | None:
    """Coerce arbitrary input to a valid category key, or None."""
    if not value:
        return None
    v = str(value).strip().lower()
    return v if v in GRADE_CATEGORIES else None


def suggest_categories(name) -> tuple[str, ...]:
    """Every category a grade name suggests, in canonical order.

    A name can genuinely say two things at once — "Girls Under 14" is a junior
    grade AND a women's grade — and forcing one answer is what
    :func:`suggest_category` had to do. Returns ('senior',) when no marker
    matches, since an undecorated grade name is the men's senior competition.
    """
    if not name:
        return ("senior",)
    n = str(name)
    found = []
    if _JUNIOR.search(n):
        found.append("junior")
    if _WOMENS.search(n):
        found.append("womens")
    if _MASTERS.search(n):
        found.append("masters")
    if _MIXED.search(n):
        found.append("mixed")
    if not found:
        return ("senior",)
    return tuple(c for c in GRADE_CATEGORIES if c in found)


def suggest_category(name) -> str:
    """Best-guess single category for a grade name. Falls back to 'senior'.

    Junior wins over women's when both markers are present, so youth age-groups
    land in Junior (the primary Senior/Junior split clubs ask for). Kept as the
    one-answer view of :func:`suggest_categories` for every reader of the
    single ``grades.category`` column.
    """
    cats = suggest_categories(name)
    for key in ("junior", "womens", "masters", "mixed"):
        if key in cats:
            return key
    return "senior"


# Format markers in a grade name. Checked t20-first: "Twenty20" holds neither
# "two" nor "one", but a club writing "T20 Two Day Qualifier" would otherwise
# read as two-day. Mirrors the substring vocabulary
# ``fees.derive_fee_format``/``iq_team._fmt_of`` already parse ``matchType``
# with, so one grade name and one CA match string can't disagree.
_T20 = re.compile(r"\b(?:t\s?/?\s?20|twenty\s?20|twenty-?20|big\s?bash)\b", re.I)
_TWO_DAY = re.compile(r"\b(?:two[\s-]?day|2[\s-]?day|2dy)\b", re.I)
_ONE_DAY = re.compile(r"\b(?:one[\s-]?day|1[\s-]?day|limited[\s-]?over|od)\b", re.I)


def normalise_format(value) -> str | None:
    """Coerce arbitrary input to a valid match-format key, or None."""
    if not value:
        return None
    v = str(value).strip().lower()
    return v if v in MATCH_FORMATS else None


def format_from_match_type(value) -> str | None:
    """Map a free-text format string to a key, or None when it says nothing.

    Takes CA's own ``matchType`` ("One Day" / "Two Day" / "T20"), a club's
    hand-typed manual-game format ("40-over", "2-day") or a ``fee_format``
    override. Deliberately returns None rather than guessing "one day" for an
    unrecognised value — ``derive_fee_format`` has to pick something because a
    match day must be billed, whereas a filter that cannot tell should say so.
    """
    v = (value or "")
    if not isinstance(v, str):
        v = str(v)
    v = v.strip().lower()
    if not v or v in {"exclude", "women", "bye"}:
        return None
    if "t20" in v or "twenty" in v:
        return "t20"
    if "two" in v or v.startswith("2 ") or v.startswith("2-") or v.startswith("2d"):
        return "two_day"
    if "one" in v or "limited" in v or v.startswith("1 ") or v.startswith("1-"):
        return "one_day"
    return None


def format_sql_case(alias: str = "g", column: str = "match_format") -> str:
    """SQL that maps a game's own ``match_format`` text to a format key.

    The SQL mirror of :func:`format_from_match_type`, and the reason a game's
    format is decided in ONE place: the column holds CA's raw ``matchType``
    ("One Day" / "Two Day" / "T20") for a synced game and whatever a club typed
    for a manual one, so every reader substring-parses it. Yields NULL for a
    string it cannot place — the filter then leaves that game out rather than
    calling it a one-dayer, which is the opposite of what
    ``fees.derive_fee_format`` has to do.

    The two are asserted to agree on a table of real strings in the verification
    suite; change one and change the other.
    """
    v = f"LOWER(COALESCE({alias}.{column}, ''))"
    return (
        "CASE"
        f" WHEN {v} LIKE '%t20%' OR {v} LIKE '%twenty%' THEN 't20'"
        f" WHEN {v} LIKE '%two%' OR {v} LIKE '2 %' OR {v} LIKE '2-%'"
        f" OR {v} LIKE '2d%' THEN 'two_day'"
        f" WHEN {v} LIKE '%one%' OR {v} LIKE '%limited%' OR {v} LIKE '1 %'"
        f" OR {v} LIKE '1-%' THEN 'one_day'"
        " ELSE NULL END"
    )


def normalise_formats(value) -> tuple[str, ...] | None:
    """Coerce a format selection to a sorted-by-canonical-order tuple, or None.

    Accepts the comma-separated string the API takes on the wire, a list (what
    the column stores) or None. None means "not specified"; an empty tuple is a
    real, if useless, empty choice — the same distinction
    ``grade_scope.normalise_categories`` draws.
    """
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        return None
    if "all" in {str(v).strip().lower() for v in raw}:
        return tuple(MATCH_FORMATS)
    picked = {f for f in (normalise_format(v) for v in raw) if f}
    return tuple(f for f in MATCH_FORMATS if f in picked)


def suggest_formats(name) -> tuple[str, ...]:
    """Format(s) a grade NAME declares, in canonical order.

    Empty when the name says nothing, which is the common case — most grade
    names ("1st Grade", "A Grade") carry no format at all. Empty means unknown,
    never "one day": a caller deciding what a grade plays should fall through to
    the games actually recorded against it rather than assume.
    """
    if not name:
        return ()
    n = str(name)
    found = set()
    if _T20.search(n):
        found.add("t20")
    if _TWO_DAY.search(n):
        found.add("two_day")
    if _ONE_DAY.search(n):
        found.add("one_day")
    return tuple(f for f in MATCH_FORMATS if f in found)


def format_label(key) -> str:
    """Human label for a match-format key (falls back to the raw key)."""
    k = normalise_format(key)
    return FORMAT_LABELS.get(k, str(key or ""))


def category_label(key) -> str:
    """Human label for a category key (falls back to the raw key)."""
    k = normalise_category(key)
    return CATEGORY_LABELS.get(k, "Senior" if k is None else str(key))


# A grade name with its trailing sponsor parenthetical removed —
# "B Grade (DXC Technology)" -> "B Grade". Only a parenthetical with no digit
# is stripped (sponsors are alphabetic; a genuine sub-grade like "(Div 1)"
# carries a number and stays distinct). Python mirror of
# services/iq_filters.py's `grade_base` SQL regex, for callers holding a plain
# string (a live Grassroots fixture/match) rather than a `grades` row.
_SPONSOR_SUFFIX = re.compile(r"\s*\([^)0-9]*\)\s*$")


def strip_sponsor_suffix(name) -> str:
    return _SPONSOR_SUFFIX.sub("", str(name or "")).strip()


def grade_key(name) -> str:
    """The key a grade name is matched on: sponsor suffix off, lowercased."""
    return strip_sponsor_suffix(name).lower()


async def grade_alias_map(db, org_id) -> dict[str, str]:
    """``{alias key: canonical key}`` from the club's active grade merges.

    Single hop, matching ``aggregations._GRADE_MATCH``: a merge is re-targeted
    onto the final canonical name when it is made, so there is no chain to
    walk. Keyed on :func:`grade_key` at both ends, so a sponsor suffix on one
    side cannot stop a merge resolving.
    """
    if not org_id:
        return {}
    from sqlalchemy import text
    res = await db.execute(
        text(
            "SELECT alias_name, canonical_name FROM grade_merge_logs"
            " WHERE org_id = CAST(:org AS UUID) AND undone_at IS NULL"
        ),
        {"org": str(org_id)},
    )
    return {grade_key(a): grade_key(c) for a, c in res.fetchall()}


def _apply_alias_fold(confirmed: dict, all_names: set, aliases: dict) -> None:
    """Let a merged-away grade name read the answer given to the one it kept.

    A club classifies "B Grade McIntosh Cup" on the Grades screen; the rows CA
    once called "B Grade: McIntosh Cup" were merged into it and never carried
    an answer of their own. Both keys have to resolve to the same category, or
    the same real grade reads two ways depending on which season's spelling a
    row happens to carry — and a shared fixture, whose grade row belongs to the
    other club, is exactly where the older spelling turns up.
    """
    for alias, canonical in aliases.items():
        all_names.add(alias)
        if alias not in confirmed and canonical in confirmed:
            confirmed[alias] = set(confirmed[canonical])


async def org_grade_categories(db, org_id) -> dict[str, str]:
    """Every distinct grade name in the org, mapped to its EFFECTIVE category —
    confirmed (any season's row sharing that name has `category` set) else the
    name-based suggestion. Keyed on the sponsor-suffix-stripped, lowercased
    name, since CA decorates a grade's name with the season's sponsor and both
    our stored rows and a live Grassroots fixture/lineup carry this — mirrors
    the "MAX(category) grouped by name" resolution `admin.py::list_grades_with_stats`
    already uses for the admin grade list.
    """
    from sqlalchemy import text
    res = await db.execute(
        text(
            "SELECT gr.name, gr.category FROM grades gr "
            "JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = :org"
        ),
        {"org": org_id},
    )
    confirmed: dict[str, str] = {}
    all_names: set[str] = set()
    for name, category in res.fetchall():
        key = strip_sponsor_suffix(name).lower()
        all_names.add(key)
        cat = normalise_category(category)
        if cat:
            confirmed[key] = cat
    for alias, canonical in (await grade_alias_map(db, org_id)).items():
        all_names.add(alias)
        if alias not in confirmed and canonical in confirmed:
            confirmed[alias] = confirmed[canonical]
    return {name: confirmed.get(name) or suggest_category(name) for name in all_names}


async def org_grade_category_sets(db, org_id) -> dict[str, frozenset]:
    """Every distinct grade name in the org, mapped to its EFFECTIVE categories.

    The multi-valued ``grades.categories`` wins; a club that only ever set the
    single ``category`` reads as that one value; a grade nobody has classified
    falls back to :func:`suggest_categories`. Keyed on the sponsor-suffix-
    stripped, lowercased name for the same reason
    :func:`org_grade_categories` is — CA decorates a grade's name with the
    season's sponsor, and one grade must not read as two.
    """
    from sqlalchemy import text
    res = await db.execute(
        text(
            "SELECT gr.name, gr.category, gr.categories FROM grades gr "
            "JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = :org"
        ),
        {"org": org_id},
    )
    confirmed: dict[str, set] = {}
    all_names: set[str] = set()
    for name, category, categories in res.fetchall():
        key = strip_sponsor_suffix(name).lower()
        all_names.add(key)
        picked = {c for c in (normalise_category(c) for c in (categories or [])) if c}
        if not picked:
            one = normalise_category(category)
            picked = {one} if one else set()
        if picked:
            # A grade name spans several seasons' rows. Union rather than
            # last-wins, so a club that classified this season's row and left an
            # older one blank keeps the answer they actually gave.
            confirmed.setdefault(key, set()).update(picked)
    _apply_alias_fold(confirmed, all_names, await grade_alias_map(db, org_id))
    return {
        name: frozenset(confirmed.get(name) or suggest_categories(name))
        for name in all_names
    }


async def org_grade_format_sets(db, org_id) -> dict[str, frozenset]:
    """Every distinct grade name in the org, mapped to the format(s) it plays.

    Three sources, in order, because a club should not have to answer a question
    the data already answers:

    1. ``grades.match_formats`` — what the club ticked on the Grades screen.
    2. The formats actually recorded on this grade's games
       (``games.match_format``, which the sync writes from CA's own
       ``matchType``). This is the accurate answer for a grade whose whole
       season is one format, and it needs no admin action at all.
    3. The grade NAME ("Women's T20 Grade 2"), for a grade with no games pulled
       yet.

    An empty set means genuinely unknown, and callers must not read it as
    one-day — that guess is right for billing a match day and wrong for a
    filter, which should leave a grade it cannot place out rather than claim it.
    """
    from sqlalchemy import text
    res = await db.execute(
        text(
            """
            SELECT gr.name,
                   gr.match_formats,
                   gr.fee_format,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.match_format), NULL) AS seen
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN v_effective_games g ON g.grade_id = gr.id
            WHERE s.organisation_id = :org
            GROUP BY gr.id, gr.name, gr.match_formats, gr.fee_format
            """
        ),
        {"org": org_id},
    )
    confirmed: dict[str, set] = {}
    observed: dict[str, set] = {}
    all_names: set[str] = set()
    for name, formats, fee_format, seen in res.fetchall():
        key = strip_sponsor_suffix(name).lower()
        all_names.add(key)
        picked = {f for f in (normalise_format(f) for f in (formats or [])) if f}
        if not picked:
            # A fee_format override is the club telling us the same thing in the
            # one place they could say it before this existed. 'exclude' and
            # 'women' are billing answers, not formats, and map to nothing.
            one = format_from_match_type(fee_format)
            picked = {one} if one else set()
        if picked:
            confirmed.setdefault(key, set()).update(picked)
        for raw in (seen or []):
            f = format_from_match_type(raw)
            if f:
                observed.setdefault(key, set()).add(f)
    aliases = await grade_alias_map(db, org_id)
    _apply_alias_fold(confirmed, all_names, aliases)
    _apply_alias_fold(observed, all_names, aliases)
    return {
        name: frozenset(
            confirmed.get(name) or observed.get(name) or suggest_formats(name)
        )
        for name in all_names
    }


def categories_for_name(categories: dict[str, frozenset], name) -> frozenset:
    """A grade's effective categories from :func:`org_grade_category_sets`'s map."""
    key = strip_sponsor_suffix(name).lower()
    got = categories.get(key)
    return got if got else frozenset(suggest_categories(name))


def formats_for_name(formats: dict[str, frozenset], name) -> frozenset:
    """A grade's effective formats from :func:`org_grade_format_sets`'s map.

    An empty frozenset is a real answer here — "we cannot tell what this grade
    plays" — not a lookup miss.
    """
    key = strip_sponsor_suffix(name).lower()
    got = formats.get(key)
    return got if got is not None else frozenset(suggest_formats(name))


def category_for_name(categories: dict[str, str], name) -> str:
    """Look up a grade's effective category from `org_grade_categories`'s map.
    Falls back to a fresh suggestion if the exact (stripped) name isn't in the
    map — shouldn't normally happen, but a live feed name could in principle
    differ slightly from anything we've stored."""
    key = strip_sponsor_suffix(name).lower()
    return categories.get(key) or suggest_category(name)
