"""Player Cards, club pack designs (migration 371): a club's own look for its packs.

`club_card_pack_designs` holds one design per TARGET: `default` (every pack that has no design of its own), a pack source
(`weekly`, `century`, `halloween`, ...) or one scheduled event (`event:<id>`). A design is a background image and a centre
image (both optional, stored here in Postgres like every other club image so they survive a container rebuild), three colours,
how dark to lay the background down, whether the pack's name and the club logo are drawn, where the centre image sits and
how big, and a name of its own for that kind of pack.

`bg_rev` / `art_rev` are the time an image was last set (NULL = no image): they go in the image URL as the cache-buster and
let the list of designs say which have images without reading the bytes.

ONE copy of the DDL: alembic's 371 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS club_card_pack_designs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        target TEXT NOT NULL,
        title TEXT,
        color_a TEXT,
        color_b TEXT,
        color_on TEXT,
        overlay DOUBLE PRECISION NOT NULL DEFAULT 0.25,
        show_name BOOLEAN NOT NULL DEFAULT TRUE,
        show_logo BOOLEAN NOT NULL DEFAULT TRUE,
        art_position TEXT NOT NULL DEFAULT 'center',
        art_size TEXT NOT NULL DEFAULT 'm',
        bg_data BYTEA,
        bg_mime TEXT,
        bg_rev BIGINT,
        art_data BYTEA,
        art_mime TEXT,
        art_rev BIGINT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_card_pack_designs_target ON club_card_pack_designs (organisation_id, target)",
]

# Drops only the table this migration added.
DOWNGRADE = ["DROP TABLE IF EXISTS club_card_pack_designs"]
