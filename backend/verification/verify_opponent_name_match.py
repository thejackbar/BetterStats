"""Verify BetterIQ resolves a fixture opponent to its stored head-to-head history
when the two feeds spell the club differently.

Reported: Gisborne CC's Opposition page showed "No history matched for
'Rupertswood 1st XI'" and "No meetings", even though Gisborne played Rupertswood
last season (a McIntyre Cup match on play.cricket). The fixtures feed keeps the
per-grade team suffix ("Rupertswood 1st XI"); our stored ``opp_club_name`` is the
same club run through ``sync.strip_team_suffix`` and usually spelled by its
owning-org name ("Rupertswood Cricket Club"), so the old exact-name lookup
(``LOWER(opp_club_name) = LOWER(:name)``) systematically missed.

These are the SHIPPED, DB-free matching helpers — no retyping, no stub. No live
call and no Postgres: the fuzzy fallback in ``_resolve_opp_key`` runs its
candidate set through exactly these functions, so pinning them pins the fix.
"""
from app.services.iq import _best_opp_key_by_name, _club_core_tokens

checks = []


def check(name, cond):
    checks.append((name, bool(cond)))


# Our stored opponents: (opp_key [a CA org GUID], representative opp_club_name).
RUPERTSWOOD_KEY = "11111111-1111-1111-1111-111111111111"
GISBORNE_HISTORY = [
    (RUPERTSWOOD_KEY, "Rupertswood Cricket Club"),
    ("22222222-2222-2222-2222-222222222222", "Woodend Cricket Club"),
    ("33333333-3333-3333-3333-333333333333", "Macedon"),
    ("44444444-4444-4444-4444-444444444444", "Riddell District"),
]

# ── The reported case, in every spelling the two feeds actually produce ──
for fixture_name in (
    "Rupertswood 1st XI",          # the fixture card / heading Gisborne saw
    "Rupertswood McIntyre 1st",    # the raw team displayName on the scorecard feed
    "Rupertswood 2nds",            # a lower-grade fixture, same club, same history
    "RUPERTSWOOD",                 # bare club name, different case
):
    hit = _best_opp_key_by_name(GISBORNE_HISTORY, fixture_name)
    check(f"'{fixture_name}' resolves to Rupertswood's stored key",
          hit is not None and hit[0] == RUPERTSWOOD_KEY)

# The old exact-equality lookup would have missed the reported name entirely.
check("the reported name is NOT an exact match of any stored club name (why exact-lookup failed)",
      not any((n or "").lower() == "rupertswood 1st xi" for _, n in GISBORNE_HISTORY))

# ── Correct identity: never latch onto a different club ──
check("a genuinely unrelated opponent name resolves to nobody",
      _best_opp_key_by_name(GISBORNE_HISTORY, "Sunbury United 1st XI") is None)
check("an empty opponent name resolves to nobody",
      _best_opp_key_by_name(GISBORNE_HISTORY, "") is None)
check("a name of only boilerplate/suffix words resolves to nobody",
      _best_opp_key_by_name(GISBORNE_HISTORY, "1st XI Cricket Club") is None)

# ── Refuse to guess between two clubs that tie ──
AMBIG = [
    ("aaaa", "Wembley Districts"),
    ("bbbb", "Wembley Downs"),
]
check("two clubs sharing the sole identifying token → refuse (no guess)",
      _best_opp_key_by_name(AMBIG, "Wembley 1st XI") is None)
# ...but the fuller name still resolves the RIGHT one of the two.
check("the fuller name still picks the exact club out of the pair",
      (_best_opp_key_by_name(AMBIG, "Wembley Districts 1sts") or (None,))[0] == "aaaa")

# A substring match outranks a bare token overlap for the same target.
MIX = [
    ("xxxx", "Rupertswood"),                # substring of the fixture name → 100
    ("yyyy", "Rupertswood Heights"),        # shares one token only → 1
]
check("a full-substring club name beats a mere token overlap",
      (_best_opp_key_by_name(MIX, "Rupertswood 1st XI") or (None,))[0] == "xxxx")

# ── Token extraction drops boilerplate + team suffix, keeps the club word ──
check("core tokens of 'Rupertswood 1st XI' are just the club word",
      _club_core_tokens("Rupertswood 1st XI") == {"rupertswood"})
check("core tokens strip 'Cricket Club' boilerplate",
      _club_core_tokens("Rupertswood Cricket Club") == {"rupertswood"})
check("a two-word club keeps both identifying words",
      _club_core_tokens("Wembley Districts CC") == {"wembley", "districts"})
check("hyphens and punctuation split into tokens",
      _club_core_tokens("St Kilda-Brighton") == {"kilda", "brighton"})

# ── The two spellings of ONE club reduce to the same core, so they match ──
check("the fixture spelling and the stored spelling share their core token",
      _club_core_tokens("Rupertswood 1st XI") & _club_core_tokens("Rupertswood Cricket Club"))

# ── Control: with the fix's token step bypassed, the reported case fails ──
# (exact equality is what the code did before — reproduce it here to show the gap)
def _exact_only(cands, target):
    t = (target or "").strip().lower()
    return next(((k, n) for k, n in cands if (n or "").strip().lower() == t), None)


check("CONTROL: exact-only lookup returns nothing for the reported case (the bug)",
      _exact_only(GISBORNE_HISTORY, "Rupertswood 1st XI") is None)


failed = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {n}")
print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
if failed:
    raise SystemExit(1)
