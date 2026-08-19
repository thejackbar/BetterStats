"""What kind of final was this, read off the association's own round name.

``games.is_final`` is one bit, and one bit cannot tell a flag from a straight-
sets exit: the sync sets it from ``"final" in round_name.lower()``, so a Grand
Final, a semi, a prelim and a qualifying final all land as ``True``. Awarding a
premiership needs the distinction, so the round name is stored on the game
(migration 264) and classified here.

The rules are deliberately plain string tests rather than anything cleverer.
A round name is free text typed by whoever runs the competition, not a code
from a fixed list, so the same match reads "Grand Final", "GRAND FINAL", "GF"
or "Final" depending on the association. Nothing here tries to guess past that:
a name we cannot place returns ``None`` and the game is simply never proposed.

**Order of the tests is load-bearing.** Every finals name contains the word
"final", so the specific kinds have to be claimed before the bare one. Check
"grand" first or "Grand Final" reads as an ordinary final; check the bare
"final" first and every semi in the competition becomes a premiership.
"""
from __future__ import annotations

import re

# The kinds, most specific first. The value is what gets stored and shown.
GRAND_FINAL = "grand_final"
FINAL = "final"
PRELIMINARY_FINAL = "preliminary_final"
QUALIFYING_FINAL = "qualifying_final"
ELIMINATION_FINAL = "elimination_final"
SEMI_FINAL = "semi_final"

LABELS = {
    GRAND_FINAL: "Grand Final",
    FINAL: "Final",
    PRELIMINARY_FINAL: "Preliminary Final",
    QUALIFYING_FINAL: "Qualifying Final",
    ELIMINATION_FINAL: "Elimination Final",
    SEMI_FINAL: "Semi Final",
}

# A premiership is won in exactly these two. A one-day or T20 competition
# often calls its decider plain "Final" and means the flag by it, so the bare
# name has to count — but it is the weaker claim of the two, which is what
# `confidence` below exists to say.
PREMIERSHIP_ROUNDS = (GRAND_FINAL, FINAL)

# Word-boundary abbreviations. Checked as whole tokens only: "gf" inside
# "Bendigo GFL Round 4" must not read as a Grand Final.
_ABBREVIATIONS = (
    (GRAND_FINAL, r"\bgf\b"),
    (PRELIMINARY_FINAL, r"\bpf\b"),
    (QUALIFYING_FINAL, r"\bqf\b"),
    (ELIMINATION_FINAL, r"\bef\b"),
    (SEMI_FINAL, r"\bsf\b"),
)

# Phrase tests, applied in this order. Each entry is (kind, substrings).
_PHRASES = (
    (GRAND_FINAL, ("grand final", "grandfinal", "grand-final")),
    (PRELIMINARY_FINAL, ("preliminary final", "prelim final", "preliminary")),
    (QUALIFYING_FINAL, ("qualifying final", "qualifier")),
    (ELIMINATION_FINAL, ("elimination final", "eliminator", "elimination")),
    (SEMI_FINAL, ("semi final", "semi-final", "semifinal", "semi")),
)


def _normalise(round_name: str | None) -> str:
    if not round_name:
        return ""
    # Collapse punctuation to spaces so "Semi-Final" and "Final (Week 3)"
    # test the same as their plain-spelled forms.
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", round_name.lower())).strip()


def classify_round(round_name: str | None) -> str | None:
    """Return the finals kind for a round name, or None if it is not a final.

    None covers both an ordinary home-and-away round ("Round 7") and a name
    we simply cannot place. Those are the same answer for our purposes: do
    not propose a premiership off it.
    """
    text = _normalise(round_name)
    if not text:
        return None

    for kind, needles in _PHRASES:
        if any(n in text for n in needles):
            return kind

    for kind, pattern in _ABBREVIATIONS:
        if re.search(pattern, text):
            return kind

    # A numbered round is home-and-away whatever else the name says. This
    # catches "Round 12 (Final Round)", which is the last ordinary round and
    # not a decider — without the guard the bare test below claims it.
    if re.search(r"\bround\s*\d+", text):
        return None

    # Bare "final" / "finals" last, so it only ever catches what nothing
    # more specific already claimed.
    if re.search(r"\bfinals?\b", text):
        return FINAL

    return None


def is_premiership_round(kind: str | None) -> bool:
    """Is a win in this round a premiership?"""
    return kind in PREMIERSHIP_ROUNDS


def confidence(kind: str | None) -> str:
    """How sure the round name alone makes us.

    'high'   — the name says Grand Final, there is nothing to second-guess.
    'review' — the name says only "Final". Usually the decider of a one-day
               or T20 competition, but some associations label a semi that
               way, so it is worth a human glance before it reaches the
               honour board.
    """
    if kind == GRAND_FINAL:
        return "high"
    if kind == FINAL:
        return "review"
    return "none"


def label(kind: str | None) -> str:
    return LABELS.get(kind or "", "")
