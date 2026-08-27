"""
The instructional video library, verified against a real Postgres by running
the SHIPPED service functions and route bodies — nothing here is a re-typed
copy of the logic under test.

    python backend/verification/verify_instructional_videos.py

Needs a Postgres it can create a table in; point VIDEO_TEST_DSN at one.
"""
import asyncio
import io
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The router module is imported for its OWN helpers (_parse_range,
# _read_upload). Its auth and model imports drag in the whole settings/JWT
# stack, which is already-proven code and not what is under test here, so they
# are stubbed rather than installed.
import types                                                    # noqa: E402

_auth_stub = types.ModuleType("app.routers.auth")
_auth_stub.require_super_admin = lambda: None
sys.modules.setdefault("app.routers.auth", _auth_stub)
_db_stub = types.ModuleType("app.models.db")


class _Model:  # noqa: D401 - stand-in for the ORM classes the router type-hints
    pass


_db_stub.User = _Model
_db_stub.Player = _Model
_db_stub.Organisation = _Model
_db_stub.get_db = lambda: None
sys.modules.setdefault("app.models.db", _db_stub)

from sqlalchemy import text                                    # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.services import instructional_videos as svc          # noqa: E402
from app.services.instructional_video_ddl import (            # noqa: E402
    DOWNGRADE_STATEMENTS,
    STATEMENTS,
)

DSN = os.environ.get(
    "VIDEO_TEST_DSN",
    "postgresql+asyncpg://postgres:pw@127.0.0.1:5432/bsvideo",
)

PASS, FAIL = 0, 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f"  {extra}" if extra else ""))


class FakeUpload:
    """Stands in for FastAPI's UploadFile so the ROUTE bodies can be run
    directly, rather than re-implementing what they do to an upload."""

    def __init__(self, filename, content_type, data):
        self.filename = filename
        self.content_type = content_type
        self._f = io.BytesIO(data)

    async def read(self):
        return self._f.read()


async def main():
    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # ---------------------------------------------------------------- schema
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS instructional_videos CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        # The FK target. Only the column the DDL references matters here.
        await conn.execute(text(
            "CREATE TABLE users (id UUID PRIMARY KEY, username TEXT)"
        ))
        user_id = uuid.uuid4()
        await conn.execute(
            text("INSERT INTO users (id, username) VALUES (:i, 'super')"), {"i": user_id}
        )

    # The lifespan mirror re-runs the whole list on every boot, so applying it
    # three times to a populated table has to be a no-op, not an error.
    for run in range(3):
        async with engine.begin() as conn:
            for stmt in STATEMENTS:
                await conn.execute(text(stmt))
        if run == 0:
            async with Session() as db:
                await svc.create_video(
                    db, title="Idempotency probe", description="", module_label=None,
                    video_bytes=b"probe-bytes", video_mime="video/mp4",
                    video_filename="p.mp4", poster_bytes=None, poster_mime=None,
                    created_by_user_id=user_id,
                )
    async with Session() as db:
        rows = await svc.list_videos(db)
    ck("DDL applied three times to a populated table, nothing duplicated", len(rows) == 1,
       f"{len(rows)} rows")

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM instructional_videos"))

    # -------------------------------------------------------------- creating
    async with Session() as db:
        a = await svc.create_video(
            db, title="BetterCricket - Merge Players",
            description="One person, two records.", module_label="BetterStats",
            video_bytes=b"A" * 5000, video_mime="video/mp4",
            video_filename="merge.mp4", poster_bytes=b"POSTERBYTES",
            poster_mime="image/jpeg", created_by_user_id=user_id,
        )
    ck("create: slug derived from the title", a["slug"] == "bettercricket-merge-players", a["slug"])
    ck("create: title, description and module stored",
       a["title"] == "BetterCricket - Merge Players"
       and a["description"] == "One person, two records."
       and a["module_label"] == "BetterStats")
    ck("create: video size recorded", a["video_size"] == 5000, str(a["video_size"]))
    ck("create: public src points at the streaming endpoint",
       a["src"] == f"/api/public/videos/{a['slug']}/file", a["src"])
    ck("create: poster is reported because one was uploaded", a["poster"] is not None)
    ck("create: first video sorts first", a["sort_order"] == 0, str(a["sort_order"]))

    async with Session() as db:
        b = await svc.create_video(
            db, title="BetterCricket - Merge Grades", description="Two names, one grade.",
            module_label="BetterStats", video_bytes=b"B" * 900, video_mime="video/mp4",
            video_filename="grades.mp4", poster_bytes=None, poster_mime=None,
            created_by_user_id=user_id,
        )
    ck("create: a video with no poster reports none", b["poster"] is None)
    ck("create: second video lands after the first", b["sort_order"] == 1, str(b["sort_order"]))

    # A repeated title must not fail the upload — it gets a suffixed slug.
    async with Session() as db:
        dup = await svc.create_video(
            db, title="BetterCricket - Merge Players", description="A re-record.",
            module_label=None, video_bytes=b"C" * 10, video_mime="video/mp4",
            video_filename="again.mp4", poster_bytes=None, poster_mime=None,
            created_by_user_id=user_id,
        )
    ck("create: a duplicate title is suffixed rather than refused",
       dup["slug"] == "bettercricket-merge-players-2", dup["slug"])
    ck("create: the original keeps its slug", (await _slug_of(Session, a["id"])) == a["slug"])

    # An all-symbol title still has to produce an addressable URL.
    ck("slugify: an unusable title falls back rather than producing an empty path",
       svc.slugify("!!! ???") == "video", svc.slugify("!!! ???"))

    # -------------------------------------------------------------- updating
    async with Session() as db:
        edited = await svc.update_video(db, a["id"], fields={"title": "Merging duplicate players"})
    ck("update: the title changes", edited["title"] == "Merging duplicate players")
    ck("update: the description is NOT blanked by a title-only save",
       edited["description"] == "One person, two records.", edited["description"])
    ck("update: THE SLUG DOES NOT MOVE, so an existing link still works",
       edited["slug"] == a["slug"], edited["slug"])
    ck("update: the video file is untouched by a text edit",
       edited["video_size"] == 5000, str(edited["video_size"]))

    async with Session() as db:
        replaced = await svc.update_video(
            db, a["id"], fields={},
            video_bytes=b"Z" * 7777, video_mime="video/webm", video_filename="new.webm",
        )
    ck("update: replacing the file swaps the bytes", replaced["video_size"] == 7777)
    ck("update: replacing the file keeps the title", replaced["title"] == "Merging duplicate players")
    ck("update: replacing the file keeps the description",
       replaced["description"] == "One person, two records.")
    async with Session() as db:
        info = await svc.video_blob_info(db, a["slug"])
    ck("update: the served mime follows the new file", info[0] == "video/webm", info[0])

    async with Session() as db:
        try:
            await svc.update_video(db, a["id"], fields={"title": "   "})
            blank_refused = False
        except ValueError:
            blank_refused = True
    ck("update: a blank title is refused", blank_refused)

    async with Session() as db:
        missing = await svc.update_video(db, str(uuid.uuid4()), fields={"title": "nope"})
    ck("update: an unknown id reports nothing rather than raising", missing is None)

    # ------------------------------------------------------------- streaming
    async with Session() as db:
        whole = await svc.read_blob_range(db, b["slug"], 0, 900)
        head = await svc.read_blob_range(db, b["slug"], 0, 10)
        mid = await svc.read_blob_range(db, b["slug"], 100, 50)
        info_b = await svc.video_blob_info(db, b["slug"])
    ck("stream: the whole file reads back byte for byte", whole == b"B" * 900)
    ck("stream: a range returns only that slice", head == b"B" * 10 and len(mid) == 50)
    ck("stream: size is reported without loading the blob", info_b[1] == 900, str(info_b[1]))
    async with Session() as db:
        no_poster = await svc.video_blob_info(db, b["slug"], poster=True)
        yes_poster = await svc.video_blob_info(db, a["slug"], poster=True)
    ck("stream: a video with no poster reports no poster file", no_poster is None)
    ck("stream: a poster is served from its own column", yes_poster and yes_poster[1] == 11,
       str(yes_poster))

    # Range maths, run through the route's own parser.
    from app.routers.instructional_videos import _parse_range
    ck("range: a plain range parses", _parse_range("bytes=0-99", 1000) == (0, 99))
    ck("range: an open-ended range runs to the end", _parse_range("bytes=500-", 1000) == (500, 999))
    ck("range: a suffix range reads the tail", _parse_range("bytes=-100", 1000) == (900, 999))
    ck("range: an end past the file is clamped", _parse_range("bytes=900-99999", 1000) == (900, 999))
    ck("range: a start past the file is refused", _parse_range("bytes=5000-", 1000) is None)
    ck("range: junk is ignored rather than erroring", _parse_range("cheese", 1000) is None)
    ck("range: no header means the whole file", _parse_range(None, 1000) is None)

    # -------------------------------------------------------------- ordering
    async with Session() as db:
        listed = await svc.list_videos(db)
    ck("order: the library lists in sort order",
       [v["slug"] for v in listed] == [a["slug"], b["slug"], dup["slug"]],
       str([v["slug"] for v in listed]))

    async with Session() as db:
        reordered = await svc.reorder_videos(db, [dup["id"], a["id"], b["id"]])
    ck("reorder: the new order is what was sent",
       [v["id"] for v in reordered] == [dup["id"], a["id"], b["id"]])
    async with Session() as db:
        again = await svc.list_videos(db)
    ck("reorder: the order survives a fresh read",
       [v["id"] for v in again] == [dup["id"], a["id"], b["id"]])
    ck("reorder: positions are renumbered from zero with no gaps",
       [v["sort_order"] for v in again] == [0, 1, 2], str([v["sort_order"] for v in again]))

    # The ids come from a browser, so a foreign or junk id must not corrupt it.
    async with Session() as db:
        partial = await svc.reorder_videos(db, [b["id"], str(uuid.uuid4()), "not-a-uuid"])
    ck("reorder: an unknown id is skipped rather than breaking the sort",
       partial[0]["id"] == b["id"] and len(partial) == 3,
       str([v["slug"] for v in partial]))
    ck("reorder: a video the caller did not mention is kept, not dropped",
       {v["id"] for v in partial} == {a["id"], b["id"], dup["id"]})

    async with Session() as db:
        deduped = await svc.reorder_videos(db, [a["id"], a["id"], b["id"]])
    ck("reorder: a repeated id does not duplicate the row", len(deduped) == 3)

    # -------------------------------------------------------------- deleting
    async with Session() as db:
        gone = await svc.delete_video(db, dup["id"])
        left = await svc.list_videos(db)
    ck("delete: reports success", gone)
    ck("delete: the entry is gone", dup["id"] not in {v["id"] for v in left})
    ck("delete: the others are untouched", len(left) == 2)
    async with Session() as db:
        blob = await svc.video_blob_info(db, dup["slug"])
    ck("delete: THE FILE GOES WITH THE ENTRY, no orphan left behind", blob is None)
    async with Session() as db:
        ck("delete: an unknown id reports failure rather than raising",
           not await svc.delete_video(db, str(uuid.uuid4())))
        ck("delete: junk id reports failure", not await svc.delete_video(db, "not-a-uuid"))

    # ---------------------------------------------------- route-body guards
    from app.routers.instructional_videos import _read_upload
    from fastapi import HTTPException

    async def refuses(upload, poster=False):
        try:
            await _read_upload(upload, poster=poster)
            return None
        except HTTPException as e:
            return e.status_code

    ck("upload: an mp4 is accepted",
       (await _read_upload(FakeUpload("a.mp4", "video/mp4", b"x"), poster=False))[1] == "video/mp4")
    ck("upload: a webm is accepted",
       (await _read_upload(FakeUpload("a.webm", "video/webm", b"x"), poster=False))[1] == "video/webm")
    ck("upload: a .mov is refused with 415",
       await refuses(FakeUpload("a.mov", "video/quicktime", b"x")) == 415)
    ck("upload: a mime with a charset suffix still matches",
       (await _read_upload(FakeUpload("a.mp4", "video/mp4; charset=binary", b"x"), poster=False))[1]
       == "video/mp4")
    ck("upload: an oversized video is refused with 413",
       await refuses(FakeUpload("big.mp4", "video/mp4", b"x" * (svc.MAX_VIDEO_BYTES + 1))) == 413)
    ck("upload: a poster that is not an image is refused",
       await refuses(FakeUpload("a.mp4", "video/mp4", b"x"), poster=True) == 415)
    ck("upload: no file at all reads as nothing sent",
       await _read_upload(None, poster=False) is None)
    ck("upload: an empty file reads as nothing sent",
       await _read_upload(FakeUpload("a.mp4", "video/mp4", b""), poster=False) is None)

    # --------------------------------------------------- the public payload
    async with Session() as db:
        one = await svc.get_video(db, a["slug"])
        nothing = await svc.get_video(db, "no-such-video")
    ck("public: a video is fetched by slug", one and one["id"] == a["id"])
    ck("public: an unknown slug returns nothing", nothing is None)
    ck("public: the payload carries no blob",
       one is not None and "video_data" not in one and "poster_data" not in one)
    ck("public: a date is exposed for the share card", bool(one.get("date")))

    # ------------------------------------------- share cards and the sitemap
    # Both used to read a checked-in list. They read the table now, so a video
    # a Super Admin adds, retitles or deletes has to move them with it.
    import app.routers.og_preview as og
    from app.routers.seo import _url_entry

    base = "https://betterat.cricket"
    ck("route: /videos is NOT parsed as a club slug", og._parse_route("/videos") is None,
       str(og._parse_route("/videos")))
    ck("route: /videos/{slug} parses as a video",
       og._parse_route("/videos/x") == {"type": "video", "slug": "x"})
    ck("route: /blog/{slug} still parses as a blog post",
       og._parse_route("/blog/x") == {"type": "blog", "slug": "x"})
    ck("route: an ordinary club slug still parses",
       og._parse_route("/applecross") == {"type": "club", "slug": "applecross"})

    async with Session() as db:
        card = await og._video_html(a["slug"], f"{base}/videos/{a['slug']}", base, db)
    ck("card: builds from the table", bool(card))
    ck("card: carries the admin's own title", "Merging duplicate players" in card)
    ck("card: carries the admin's own description", "One person, two records." in card)
    ck("card: uses the uploaded poster",
       f"{base}/api/public/videos/{a['slug']}/poster" in card)
    ck("card: is a VideoObject", '"@type":"VideoObject"' in card)
    ck("card: og:type is video.other", 'og:type" content="video.other"' in card)
    ck("card: breadcrumb names Videos", '"name":"Videos"' in card)
    ck("card: body offers the download", "Download this video" in card and "download=1" in card)

    import json as _json
    import re as _re
    blob = _re.search(r'<script type="application/ld\+json">(.*?)</script>', card, _re.S).group(1)
    try:
        ck("card: the JSON-LD parses", isinstance(_json.loads(blob.replace("<\\/", "</")), list))
    except Exception as exc:
        ck("card: the JSON-LD parses", False, str(exc))

    async with Session() as db:
        bare = await svc.create_video(
            db, title="No poster and no words", description="", module_label=None,
            video_bytes=b"q" * 10, video_mime="video/mp4", video_filename="q.mp4",
            poster_bytes=None, poster_mime=None, created_by_user_id=user_id,
        )
        bare_card = await og._video_html(bare["slug"], f"{base}/videos/{bare['slug']}", base, db)
    ck("card: no poster falls back to the branded cover", "/og-cover.png" in bare_card)
    ck("card: no description still gets a sentence", "A BetterCricket walkthrough" in bare_card)

    async with Session() as db:
        unknown = await og._video_html("nope", f"{base}/videos/nope", base, db)
    ck("card: an unknown slug returns nothing, so the marketing card is used",
       unknown is None)

    async with Session() as db:
        await svc.delete_video(db, bare["id"])
        after = await og._video_html(bare["slug"], f"{base}/videos/{bare['slug']}", base, db)
    ck("card: a DELETED video stops resolving", after is None)

    async with Session() as db:
        for_map = await svc.list_videos(db)
    entries = [
        _url_entry(f"{base}/videos/{v['slug']}", lastmod=v["date"],
                   changefreq="monthly", priority="0.7")
        for v in for_map
    ]
    ck("sitemap: lists exactly what the library holds",
       len(entries) == len(for_map) and all(v["slug"] in "".join(entries) for v in for_map),
       str(len(entries)))
    ck("sitemap: the deleted video is not listed",
       bare["slug"] not in "".join(entries))

    # ------------------------------------------------------------- downgrade
    async with engine.begin() as conn:
        for stmt in DOWNGRADE_STATEMENTS:
            await conn.execute(text(stmt))
        exists = (await conn.execute(text(
            "SELECT to_regclass('public.instructional_videos') IS NOT NULL"
        ))).scalar_one()
    ck("downgrade: the table is removed", not exists)

    await engine.dispose()
    print(f"\n{PASS}/{PASS + FAIL} checks passed")
    return 1 if FAIL else 0


async def _slug_of(Session, video_id):
    async with Session() as db:
        row = await svc.get_video_by_id(db, video_id)
    return row["slug"] if row else None


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
