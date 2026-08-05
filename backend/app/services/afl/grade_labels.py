"""AFL grade category labels + auto-classification.

Sibling to cricket's app/services/grade_labels.py, ported for AFL's own
category set and terminology rather than reusing cricket's directly: cricket's
suggestion regexes key on cricket-specific junior-program names (Milo,
Kanga, In2Cricket) that mean nothing in an AFL grade name, and cricket has no
"Integrated" category at all (AFL's disability-inclusive competition, a
distinct thing from a general "mixed/social" bucket). ``strip_sponsor_suffix``
has no sport-specific logic at all, so it's imported from the shared module
rather than duplicated.
"""
import re

from app.services.grade_labels import strip_sponsor_suffix  # noqa: F401 (re-exported)

GRADE_CATEGORIES = ("senior", "colts", "womens", "masters", "integrated")

CATEGORY_LABELS = {
    "senior": "Senior",
    "colts": "Colts",
    "womens": "Women's",
    "masters": "Masters",
    "integrated": "Integrated",
}

# Colts wins over women's when both markers are present, so a youth
# competition (e.g. "Girls U16") lands in Colts — the age-group split a club
# reaches for first, same precedence cricket's own junior/women's check uses.
# The `s?` after each age number is load-bearing: clubs write "Under 18s" and
# "U16s" far more often than the singular, and \b can't match between the
# digit and a trailing "s", so without it every plural age group fell through
# to 'senior'.
_COLTS = re.compile(
    r"\b(?:colts?|under[\s-]?\d+s?|u\d+s?|youth|junior[s]?|year[\s-]?\d+s?|yr[\s-]?\d+s?|auskick)\b",
    re.I,
)
_WOMENS = re.compile(r"\b(?:women'?s?|woman|ladies|lady|girls?|female)\b", re.I)
_MASTERS = re.compile(r"\b(?:masters?|veterans?|vets?|over[\s-]?\d+s?|superules?)\b", re.I)
_INTEGRATED = re.compile(
    r"\b(?:integrated|inclusion|inclusive|all[\s-]?abilities|special needs?|disability)\b",
    re.I,
)


def normalise_category(value) -> str | None:
    """Coerce arbitrary input to a valid category key, or None."""
    if not value:
        return None
    v = str(value).strip().lower()
    return v if v in GRADE_CATEGORIES else None


def suggest_category(name) -> str:
    """Best-guess category for a grade name. Falls back to 'senior'."""
    if not name:
        return "senior"
    n = str(name)
    if _COLTS.search(n):
        return "colts"
    if _INTEGRATED.search(n):
        return "integrated"
    if _WOMENS.search(n):
        return "womens"
    if _MASTERS.search(n):
        return "masters"
    return "senior"


def category_label(key) -> str:
    """Human label for a category key (falls back to the raw key)."""
    k = normalise_category(key)
    return CATEGORY_LABELS.get(k, "Senior" if k is None else str(key))
