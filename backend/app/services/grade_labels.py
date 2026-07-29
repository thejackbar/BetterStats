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
    "senior": "Senior",
    "junior": "Junior",
    "womens": "Women's",
    "masters": "Masters",
    "mixed": "Mixed / Other",
}

# Age-group / youth markers. Anything with an explicit age or youth programme
# name is a junior grade, regardless of gender, because that is the split clubs
# reach for first ("Girls U14" is a junior team).
_JUNIOR = re.compile(
    r"\b(?:under[\s-]?\d+|u\d+|colts?|juniors?|youth|year[\s-]?\d+|yr[\s-]?\d+"
    r"|milo|blaster|master[\s-]?blaster|kanga|in2cricket|woolworths)\b",
    re.I,
)
_WOMENS = re.compile(
    r"\b(?:women'?s?|woman|ladies|lady|girls?|female|pswl)\b",
    re.I,
)
_MASTERS = re.compile(
    r"\b(?:masters?|veterans?|vets?|over[\s-]?\d+|super[\s-]?rules|legends)\b",
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


def suggest_category(name) -> str:
    """Best-guess category for a grade name. Falls back to 'senior'.

    Junior wins over women's when both markers are present, so youth age-groups
    land in Junior (the primary Senior/Junior split clubs ask for).
    """
    if not name:
        return "senior"
    n = str(name)
    if _JUNIOR.search(n):
        return "junior"
    if _WOMENS.search(n):
        return "womens"
    if _MASTERS.search(n):
        return "masters"
    if _MIXED.search(n):
        return "mixed"
    return "senior"


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
    return {name: confirmed.get(name) or suggest_category(name) for name in all_names}


def category_for_name(categories: dict[str, str], name) -> str:
    """Look up a grade's effective category from `org_grade_categories`'s map.
    Falls back to a fresh suggestion if the exact (stripped) name isn't in the
    map — shouldn't normally happen, but a live feed name could in principle
    differ slightly from anything we've stored."""
    key = strip_sponsor_suffix(name).lower()
    return categories.get(key) or suggest_category(name)
