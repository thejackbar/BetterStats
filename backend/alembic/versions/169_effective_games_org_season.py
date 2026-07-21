"""v_effective_games — carry season_id/organisation_id directly, fix manual-game visibility + cross-org leak

**Bug 1 (the reported one)**: a manually-uploaded scorecard (via
/admin/upload-scorecard) with no grade picked (the upload form allows
"— none —" for Grade) never appeared on the club's public games list
(`/{slug}/games` → `GET /organisations/{id}/results`). That endpoint derives
season purely by joining `grades gr ON gr.id = g.grade_id` then
`seasons s ON s.id = gr.season_id` — with `grade_id` NULL, both `gr` and `s`
come back NULL, so the season filter (`s.id = :season_id ...`) can never
match, even though `manual_games.season_id` itself is set (it's a required
field on that table). The public Games page always applies a season filter
(it auto-selects the most recent season on load), so the row was silently
excluded under every season.

**Bug 2 (found while fixing #1)**: the same query's org-ownership check
included a bare `g.source = 'manual'` clause with no organisation check at
all — so literally any club's manual game was considered "ours" on every
other club's `/organisations/{id}/results` and `/games` (recent games) calls,
a cross-club data leak. `games.py::list_games`'s `api_games` sub-query had
the identical clause even though manual games are ALREADY fetched separately
and correctly (org-scoped) by `_fetch_manual_games_as_list` in the same
function — so that endpoint doubly leaked (any org's manual game) AND
duplicated (this org's own manual games appeared twice, once via each path).

Fix: give the view real `season_id`/`organisation_id` columns for BOTH
branches (derived via grade->season for `games`, direct columns for
`manual_games`, which always has both set). Appended at the end — existing
consumers don't reference them and none do `SELECT *` against this view (this
is the same append-only discipline migration 167 used for `home_org_id`/
`away_org_id`).

Revision ID: 169
Revises: 168
Create Date: 2026-07-21
"""
from alembic import op


revision = '169'
down_revision = '168'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW v_effective_games AS
        SELECT
            g.id, g.grade_id, g.played_at, g.home_team, g.away_team,
            g.home_club, g.away_club, g.opp_org_id, g.opp_club_name,
            g.result, g.winning_team, g.is_final,
            g.raw_payload, g.venue, g.match_format,
            'api'::text AS source,
            g.home_org_id, g.away_org_id,
            gr.season_id AS season_id,
            s.organisation_id AS organisation_id
        FROM games g
        LEFT JOIN grades gr ON gr.id = g.grade_id
        LEFT JOIN seasons s ON s.id = gr.season_id
        UNION ALL
        SELECT
            mg.id, mg.grade_id, mg.played_at, mg.home_team, mg.away_team,
            NULL::text AS home_club,
            NULL::text AS away_club,
            NULL::text AS opp_org_id,
            mg.opposition AS opp_club_name,
            mg.result, mg.winning_team, mg.is_final,
            NULL::jsonb AS raw_payload,
            mg.venue, mg.match_format,
            'manual'::text AS source,
            NULL::uuid AS home_org_id,
            NULL::uuid AS away_org_id,
            mg.season_id AS season_id,
            mg.organisation_id AS organisation_id
        FROM manual_games mg
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW v_effective_games AS
        SELECT
            id, grade_id, played_at, home_team, away_team,
            home_club, away_club, opp_org_id, opp_club_name,
            result, winning_team, is_final,
            raw_payload, venue, match_format,
            'api'::text AS source,
            home_org_id, away_org_id
        FROM games
        UNION ALL
        SELECT
            id, grade_id, played_at, home_team, away_team,
            NULL::text AS home_club,
            NULL::text AS away_club,
            NULL::text AS opp_org_id,
            opposition AS opp_club_name,
            result, winning_team, is_final,
            NULL::jsonb AS raw_payload,
            venue, match_format,
            'manual'::text AS source,
            NULL::uuid AS home_org_id,
            NULL::uuid AS away_org_id
        FROM manual_games
    """)
