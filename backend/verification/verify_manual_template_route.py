"""The manual-games CSV template downloads the template, not a routing error.

Reported by Hamilton Veterans: "Download template" on Manual Entries handed
back a 35-byte file whose body was {"detail":"Invalid manual game id"}. Cause:
`GET /games/{game_id}` was registered before `GET /games/template.csv`, and
`{game_id}` is a single path segment, so it captured the literal
"template.csv" and 422'd through `_to_uuid`. The frontend then saved that error
body as `manual_games_template.csv`.

This asserts, via Starlette's own route matching, that `/games/template.csv`
now resolves to `games_template` and a real game id still resolves to
`get_manual_game`. No database needed. Run it against the previous commit and
the first check fails (it resolves to get_manual_game instead).

    python -m verification.verify_manual_template_route
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from starlette.routing import Match

from app.routers.manual_entries import router

P = "/club-admin/manual-entries"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def first_get_match(path: str):
    """The endpoint name of the FIRST route that fully matches a GET on `path`,
    mirroring how FastAPI dispatches (registration order, first full match)."""
    scope = {"type": "http", "method": "GET", "path": path, "headers": [], "path_params": {}}
    for r in router.routes:
        matched, _ = r.matches(scope)
        if matched == Match.FULL:
            return r.endpoint.__name__
    return None


def main() -> int:
    tmpl = first_get_match(f"{P}/games/template.csv")
    check("GET /games/template.csv resolves to games_template, not the game-id route",
          tmpl == "games_template", f"resolved to {tmpl}")

    gid = first_get_match(f"{P}/games/123e4567-e89b-12d3-a456-426614174000")
    check("a real game id still resolves to get_manual_game",
          gid == "get_manual_game", f"resolved to {gid}")

    lst = first_get_match(f"{P}/games")
    check("the games list is unaffected", lst == "list_manual_games", f"resolved to {lst}")

    # There is exactly one games_template route (the old duplicate was removed,
    # not left behind to fight the moved one).
    tmpl_routes = [r for r in router.routes if r.endpoint.__name__ == "games_template"]
    check("exactly one games_template route is registered",
          len(tmpl_routes) == 1, f"found {len(tmpl_routes)}")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
