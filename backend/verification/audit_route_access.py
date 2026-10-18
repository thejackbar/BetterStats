"""Route access audit: no signed-in route ships open by accident.

Every route that needs a login must either declare what it needs (a capability,
`require_full_admin`, or staff-only) or be on `OPEN_TO_ANY_CLUB_USER` below with
the reason it is open. A person a Primary Admin has locked to one module
(services/access.py) holds only their module's capabilities, so an undeclared
route is one they can reach whatever module they are locked to.

Fails (exit 1) when:
  * a signed-in route declares nothing and is not listed here, or
  * a listed route no longer exists or has since been gated (the list only
    shrinks; a stale entry hides the next route that reuses the path).

    python -m verification.audit_route_access
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:5432/verify_user_access")

from fastapi.routing import APIRoute  # noqa: E402

from app.main import app  # noqa: E402

WHO_AM_I = 'who you are and which club you act in'
PERSONAL = "a person's own screen settings, bookmarks and inbox"
WIZARD_READ = 'setup wizard progress, read only'
PLAN_INLINE = "plan and money: checked inside the handler against the club's Primary Admin or full admins, and a locked person is neither"
STATLAB_INLINE = 'any signed-in club user may save a report; approval and deletion are checked inside the handler'
SIGNUP = 'sign-up and claim flows that run before a user has a club role'
PLAYER_REGISTER = "the club's player register, the picker every screen shares: names, grade, status, no date of birth or contacts"
PUBLIC_EQUIVALENT = 'club data the public site already shows (stats, fixtures, grades, sponsors, club branding)'

# (method, path) -> why any signed-in club user may call it. Exact entries, not
# prefixes, so a new route under the same prefix is caught.
OPEN_TO_ANY_CLUB_USER: dict[tuple[str, str], str] = {
    ("GET", "/admin/competitions"): PUBLIC_EQUIVALENT,
    ("GET", "/admin/competitions/grouping"): PUBLIC_EQUIVALENT,
    ("GET", "/admin/grades-with-stats"): PUBLIC_EQUIVALENT,
    ("GET", "/admin/juniors/preview"): PUBLIC_EQUIVALENT,
    ("GET", "/auth/me"): WHO_AM_I,
    ("POST", "/auth/switch-club"): WHO_AM_I,
    ("GET", "/club-admin/account/ui-prefs"): PERSONAL,
    ("PATCH", "/club-admin/account/ui-prefs"): PERSONAL,
    ("PUT", "/club-admin/billing/billing-method"): PLAN_INLINE,
    ("POST", "/club-admin/billing/checkout-session"): PLAN_INLINE,
    ("POST", "/club-admin/billing/invoices/request"): PLAN_INLINE,
    ("POST", "/club-admin/billing/invoices/{invoice_id}/resend"): PLAN_INLINE,
    ("POST", "/club-admin/billing/payment-methods/setup-session"): PLAN_INLINE,
    ("DELETE", "/club-admin/billing/payment-methods/{pm_id}"): PLAN_INLINE,
    ("POST", "/club-admin/billing/payment-methods/{pm_id}/default"): PLAN_INLINE,
    ("DELETE", "/club-admin/bookmarks"): PERSONAL,
    ("GET", "/club-admin/bookmarks"): PERSONAL,
    ("POST", "/club-admin/bookmarks"): PERSONAL,
    ("GET", "/club-admin/broadcasts"): PERSONAL,
    ("POST", "/club-admin/broadcasts/seen"): PERSONAL,
    ("POST", "/club-admin/broadcasts/{broadcast_id}/dismiss"): PERSONAL,
    ("POST", "/club-admin/coupons/redeem"): PLAN_INLINE,
    ("GET", "/club-admin/games"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/grades"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/member-portal/status"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/milestones"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/module-requests"): PLAN_INLINE,
    ("POST", "/club-admin/module-requests"): PLAN_INLINE,
    ("POST", "/club-admin/modules/{module_key}/cancel"): PLAN_INLINE,
    ("POST", "/club-admin/modules/{module_key}/start-trial"): PLAN_INLINE,
    ("GET", "/club-admin/notifications/count"): PERSONAL,
    ("GET", "/club-admin/notifications/feed"): PERSONAL,
    ("POST", "/club-admin/notifications/feed/read"): PERSONAL,
    ("POST", "/club-admin/notifications/seen"): PERSONAL,
    ("GET", "/club-admin/notifications/settings"): PERSONAL,
    ("PUT", "/club-admin/notifications/settings/preferences/{event_key}"): PERSONAL,
    ("POST", "/club-admin/notifications/settings/test-email"): PERSONAL,
    ("GET", "/club-admin/notifications/summary"): PERSONAL,
    ("GET", "/club-admin/onboarding-wizard/flow"): WIZARD_READ,
    ("GET", "/club-admin/onboarding-wizard/state"): WIZARD_READ,
    ("GET", "/club-admin/partnership-records"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/partnership-records/template"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/players"): PLAYER_REGISTER,
    ("GET", "/club-admin/primary-admin"): PLAN_INLINE,
    ("POST", "/club-admin/primary-admin/transfer"): PLAN_INLINE,
    ("GET", "/club-admin/season-merges"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/seasons"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/settings"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/sponsors"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/sponsors/post-default"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/sponsors/post-defaults"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/sponsors/section-names"): PUBLIC_EQUIVALENT,
    ("GET", "/club-admin/sponsors/settings"): PUBLIC_EQUIVALENT,
    ("GET", "/fixtures"): PUBLIC_EQUIVALENT,
    ("GET", "/ladders/teams"): PUBLIC_EQUIVALENT,
    ("POST", "/organisations/onboard"): SIGNUP,
    ("GET", "/organisations/search"): SIGNUP,
    ("POST", "/players/{player_id}/claim"): SIGNUP,
    ("POST", "/statlab/reports"): STATLAB_INLINE,
    ("GET", "/statlab/reports/pending"): STATLAB_INLINE,
    ("GET", "/statlab/reports/pending/count"): STATLAB_INLINE,
    ("DELETE", "/statlab/reports/{report_id}"): STATLAB_INLINE,
    ("PATCH", "/statlab/reports/{report_id}"): STATLAB_INLINE,
    ("POST", "/statlab/reports/{report_id}/review"): STATLAB_INLINE,
}


def _flat(dep):
    out = []
    for d in dep.dependencies:
        out.append(d)
        out += _flat(d)
    return out


def classify(route: APIRoute):
    """('gated'|'staff'|'public'|'signed_in', detail) for one route."""
    deps = _flat(route.dependant)
    names = {getattr(d.call, "__name__", "") for d in deps}
    caps: set[str] = set()
    full = False
    for d in deps:
        caps |= set(getattr(d.call, "required_caps", ()) or ())
        full = full or bool(getattr(d.call, "full_admin_only", False))
    if caps or full:
        return "gated", sorted(caps) or ["full admin"]
    if any("super" in n or "sales" in n for n in names):
        return "staff", []
    if names & {"get_current_user", "get_current_club"}:
        return "signed_in", []
    return "public", []


def audit() -> dict:
    counts = {"gated": 0, "staff": 0, "public": 0, "signed_in": 0}
    undeclared: list[tuple[str, str]] = []
    seen_open: set[tuple[str, str]] = set()
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        kind, _ = classify(r)
        for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
            counts[kind] += 1
            if kind == "signed_in":
                if (m, r.path) in OPEN_TO_ANY_CLUB_USER:
                    seen_open.add((m, r.path))
                else:
                    undeclared.append((m, r.path))
    stale = sorted(set(OPEN_TO_ANY_CLUB_USER) - seen_open)
    return {"counts": counts, "undeclared": sorted(undeclared, key=lambda x: (x[1], x[0])), "stale": stale}


def main() -> int:
    res = audit()
    print("routes by kind:", res["counts"])
    bad = 0
    for m, p in res["undeclared"]:
        bad += 1
        print(f"  FAIL  {m:6} {p}  signed-in route declares no capability and is not on the open list")
    for m, p in res["stale"]:
        bad += 1
        print(f"  FAIL  {m:6} {p}  on the open list but gated or gone: remove it")
    if not bad:
        print("  PASS  every signed-in route declares a capability or is on the open list with a reason")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
