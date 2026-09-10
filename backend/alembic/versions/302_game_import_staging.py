"""The parsed sheet is held server-side, not carried by the browser

A club's recovered archive is 97 seasons, 7,915 matches and 184,661 rows — one
`manual_games_scorecards.csv` of about 24 MB — and it could not be imported at
all. Raising the 8 MB cap on the upload alone would not have helped, because
the upload was never the binding limit.

THE IMPORT IS PREVIEW -> RESOLVE -> COMMIT AND ONLY PREVIEW TAKES A FILE. The
browser held the parsed rows and posted every one of them back as JSON on the
other two steps. Measured on a 33 MB, 182,154-row sheet, the same rows as a
JSON body are **145.6 MB** — all 33 column names repeat on every row — and
`resolve` fires AGAIN on every override change, so that body went back up the
wire once per player matched, season picked and grade named.

The server-side work was never the problem: `_resolve_games` over that sheet is
1.9s. The whole interactive cost was the upload. So the rows are parsed once,
at preview, stored here under a short-lived token scoped to the club and the
user, and `resolve`/`commit` take the token instead — a few hundred bytes.

`rows` STAYS ON THE REQUEST. A caller posting rows directly is byte-for-byte
unaffected; the token is an alternative, never a requirement.

TRANSIENT BY CONSTRUCTION, so a table rather than the media volume: these rows
live for one sitting of the wizard and are deleted the moment it commits, which
is the opposite of the videos volume's reason for sitting outside the backup
(a video is permanent and merely too big to dump). A table also makes expiry
and club scoping one DELETE rather than a directory walk, and this is text.

Numbered 302 after checking `origin/main`, which had reached 301 — two
migrations sharing a revision id break Alembic outright.
"""

from alembic import op
from sqlalchemy import text

from app.services.game_import_staging_ddl import STATEMENTS

revision = "302"
down_revision = "301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.execute(text(stmt))


def downgrade() -> None:
    # The table holds nothing but half-finished imports, so dropping it loses
    # no club's work — anyone mid-wizard re-uploads their sheet.
    op.get_bind().execute(text("DROP TABLE IF EXISTS manual_game_import_staging"))
