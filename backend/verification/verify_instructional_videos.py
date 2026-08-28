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
import tempfile
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

# Video files live on disk now, so the suite gets its own scratch directory
# instead of writing into /mnt/media.
#
# THIS MUST RUN BEFORE app.services.instructional_videos IS IMPORTED. That
# module imports app.config.settings, and pydantic-settings reads the
# environment once, at instantiation. Setting the variable further down the
# file looks right and silently writes to the real path.
_TMP_VIDEOS = tempfile.mkdtemp(prefix="bs-videos-")
os.environ["VIDEO_STORAGE_DIR"] = _TMP_VIDEOS

from sqlalchemy import text                                    # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.services import instructional_videos as svc          # noqa: E402
from app.services.instructional_video_ddl import (            # noqa: E402
    DOWNGRADE_STATEMENTS,
    DURATION_DOWNGRADE,
    DURATION_STATEMENTS,
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
    directly, rather than re-implementing what they do to an upload.

    `file` is the seekable handle the real UploadFile exposes, which is what
    the size check measures and what the service streams to disk."""

    def __init__(self, filename, content_type, data):
        self.filename = filename
        self.content_type = content_type
        self.file = io.BytesIO(data)

    async def read(self):
        return self.file.read()


def stream(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


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
            for stmt in STATEMENTS + DURATION_STATEMENTS:
                await conn.execute(text(stmt))
        if run == 0:
            async with Session() as db:
                await svc.create_video(
                    db, title="Idempotency probe", description="", module_label=None,
                    video_stream=stream(b"probe-bytes"), video_mime="video/mp4",
                    video_filename="p.mp4", poster_bytes_data=None, poster_mime=None,
                    created_by_user_id=user_id,
                )
    async with Session() as db:
        rows = await svc.list_videos(db)
    ck("DDL applied three times to a populated table, nothing duplicated", len(rows) == 1,
       f"{len(rows)} rows")

    # Deleted by hand in SQL, bypassing delete_video — which is exactly the
    # case orphaned_files() exists to report, so assert it does before cleaning
    # up. A row removed outside the app leaves its file behind, and these files
    # are outside the backup, so being able to find them matters.
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM instructional_videos"))
    async with Session() as db:
        stranded = await svc.orphaned_files(db)
    ck("orphan detection: a row deleted outside the app leaves a findable file",
       len(stranded) == 1, str(stranded))
    for name in stranded:
        svc.resolve_path(name).unlink(missing_ok=True)
    async with Session() as db:
        ck("orphan detection: reports nothing once cleaned up",
           await svc.orphaned_files(db) == [])

    # -------------------------------------------------------------- creating
    async with Session() as db:
        a = await svc.create_video(
            db, title="BetterCricket - Merge Players",
            description="One person, two records.", module_label="BetterStats",
            video_stream=stream(b"A" * 5000), video_mime="video/mp4",
            video_filename="merge.mp4", poster_bytes_data=b"POSTERBYTES",
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
            module_label="BetterStats", video_stream=stream(b"B" * 900), video_mime="video/mp4",
            video_filename="grades.mp4", poster_bytes_data=None, poster_mime=None,
            created_by_user_id=user_id,
        )
    ck("create: a video with no poster reports none", b["poster"] is None)
    ck("create: second video lands after the first", b["sort_order"] == 1, str(b["sort_order"]))

    # A repeated title must not fail the upload — it gets a suffixed slug.
    async with Session() as db:
        dup = await svc.create_video(
            db, title="BetterCricket - Merge Players", description="A re-record.",
            module_label=None, video_stream=stream(b"C" * 10), video_mime="video/mp4",
            video_filename="again.mp4", poster_bytes_data=None, poster_mime=None,
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
            video_stream=stream(b"Z" * 7777), video_mime="video/webm", video_filename="new.webm",
        )
    ck("update: replacing the file swaps the bytes", replaced["video_size"] == 7777)
    ck("update: replacing the file keeps the title", replaced["title"] == "Merging duplicate players")
    ck("update: replacing the file keeps the description",
       replaced["description"] == "One person, two records.")
    async with Session() as db:
        info = await svc.video_file(db, a["slug"])
    ck("update: the served mime follows the new file", info[1] == "video/webm", info[1])

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

    # ------------------------------------------------- files, not blobs
    from pathlib import Path as _Path
    store = _Path(_TMP_VIDEOS)

    async with Session() as db:
        found = await svc.video_file(db, b["slug"])
    ck("file: the video is on disk, not in the row", found is not None)
    ck("file: it holds exactly what was uploaded",
       found and found[0].read_bytes() == b"B" * 900)
    ck("file: size is read from disk", found and found[2] == 900, str(found and found[2]))
    # mkstemp writes 0600, which leaves a public video readable by root alone:
    # the host user cannot copy it back off without sudo, and nginx could not
    # serve it if the hand-off were switched on.
    import stat as _stat
    mode = _stat.S_IMODE(found[0].stat().st_mode) if found else 0
    ck("file: written world-readable, not root-only", mode == 0o644, oct(mode))

    ck("file: named after the row id, never the upload's filename",
       found and found[0].name == f"{b['id']}.mp4", found and found[0].name)

    async with Session() as db:
        row = await svc.get_video(db, b["slug"])
    ck("file: the payload reports the file is present", row["file_present"])
    ck("file: the payload carries no path a browser could use",
       "video_path" not in row and "video_data" not in row)

    # THE COLUMN MUST BE GONE, or pg_dump still carries every video and moving
    # them to disk bought nothing.
    async with engine.begin() as conn:
        cols = set((await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'instructional_videos'"
        ))).scalars().all())
    ck("file: there is NO video_data column left for pg_dump to carry",
       "video_data" not in cols, str(sorted(c for c in cols if "video" in c)))
    ck("file: the poster IS still a column, so a restored library still draws",
       "poster_data" in cols)

    # A filename is never built from anything a person typed.
    ck("safety: a traversal path does not resolve",
       svc.resolve_path("../../etc/passwd") is None)
    ck("safety: an absolute path does not resolve", svc.resolve_path("/etc/passwd") is None)
    ck("safety: a plausible-but-foreign name does not resolve",
       svc.resolve_path("evil.mp4") is None)
    ck("safety: an unexpected extension does not resolve",
       svc.resolve_path(f"{b['id']}.sh") is None)
    ck("safety: our own name does resolve", svc.resolve_path(f"{b['id']}.mp4") is not None)

    # The poster still comes out of Postgres.
    async with Session() as db:
        poster = await svc.poster_bytes(db, a["slug"])
        no_poster = await svc.poster_bytes(db, b["slug"])
    ck("poster: served from the column", poster and poster[0] == b"POSTERBYTES")
    ck("poster: a video with none reports none", no_poster is None)

    # A MISSING FILE IS AN ORDINARY STATE — these are outside the backup, so a
    # restored database legitimately has rows whose files are gone.
    async with Session() as db:
        orphan = await svc.create_video(
            db, title="Restored from a backup", description="", module_label=None,
            video_stream=stream(b"gone" * 10), video_mime="video/mp4",
            video_filename="g.mp4", poster_bytes_data=b"IMG", poster_mime="image/jpeg",
            created_by_user_id=user_id,
        )
    svc.resolve_path(f"{orphan['id']}.mp4").unlink()
    async with Session() as db:
        after = await svc.get_video(db, orphan["slug"])
        missing = await svc.video_file(db, orphan["slug"])
        still_poster = await svc.poster_bytes(db, orphan["slug"])
    ck("missing file: the row survives and still lists", after is not None)
    ck("missing file: it reports the file is NOT present", after["file_present"] is False)
    ck("missing file: serving it reports nothing rather than raising", missing is None)
    ck("missing file: the title and description are intact",
       after["title"] == "Restored from a backup")
    ck("missing file: THE THUMBNAIL STILL DRAWS, because the poster is in Postgres",
       still_poster is not None and still_poster[0] == b"IMG")

    # Replacing a file removes the old one rather than leaving it behind.
    async with Session() as db:
        before_name = f"{b['id']}.mp4"
        await svc.update_video(db, b["id"], fields={},
                               video_stream=stream(b"W" * 40), video_mime="video/webm",
                               video_filename="w.webm")
        swapped = await svc.video_file(db, b["slug"])
    ck("replace: the new file is on disk", swapped and swapped[0].read_bytes() == b"W" * 40)
    ck("replace: the extension follows the new format",
       swapped and swapped[0].name.endswith(".webm"), swapped and swapped[0].name)
    ck("replace: THE OLD FILE IS REMOVED, not orphaned",
       not (store / before_name).exists())

    async with Session() as db:
        ck("replace: nothing is orphaned afterwards", await svc.orphaned_files(db) == [],
           str(await svc.orphaned_files(db)))

    # A failed insert must not leave a file nothing points at.
    files_before = {p.name for p in store.iterdir()}
    async with Session() as db:
        try:
            await svc.create_video(
                db, title=None, description="", module_label=None,
                video_stream=stream(b"orphan-me"), video_mime="video/mp4",
                video_filename="x.mp4", poster_bytes_data=None, poster_mime=None,
                created_by_user_id=user_id,
            )
        except Exception:
            await db.rollback()
    ck("failed insert: leaves no file behind",
       {p.name for p in store.iterdir()} == files_before,
       str({p.name for p in store.iterdir()} - files_before))

    # ------------------------------------------------- what one response carries
    # Reported live: a 96MB video 404'd from nginx while the API said the file
    # was present. Two separate faults behind it, both covered here.
    from app.routers.instructional_videos import CHUNK_BYTES, stream_video

    class FakeRequest:
        """Stands in for Starlette's Request. Carries `method` as well as
        headers, because the handler branches on it — a stub that models less
        than the real object crashes the code under test rather than testing
        it."""

        def __init__(self, headers, method="GET"):
            self.headers = headers
            self.method = method

    async with Session() as db:
        big = await svc.create_video(
            db, title="A big one", description="", module_label=None,
            video_stream=stream(b"V" * (CHUNK_BYTES * 3)), video_mime="video/mp4",
            video_filename="big.mp4", poster_bytes_data=None, poster_mime=None,
            created_by_user_id=user_id,
        )

    # Chrome opens a video with `Range: bytes=0-`, which asks for the WHOLE
    # file. One response must not carry all of it, or a 96MB video is 96MB of
    # memory per viewer.
    async with Session() as db:
        r = await stream_video(big["slug"], FakeRequest({"range": "bytes=0-"}), 0, db)
    ck("serving: an open-ended range is clamped to one chunk, not the whole file",
       r.status_code == 206 and len(getattr(r, "body", b"") or b"") == CHUNK_BYTES,
       f"status {r.status_code}, {len(getattr(r, 'body', b'') or b'')} bytes")
    # .get, not [] — a check that raises takes the whole suite down with it and
    # tells you less than a plain FAIL does.
    ck("serving: it reports the partial range honestly",
       r.headers.get("content-range") == f"bytes 0-{CHUNK_BYTES - 1}/{CHUNK_BYTES * 3}",
       r.headers.get("content-range"))
    ck("serving: and says the full size so the player knows what it is getting",
       (r.headers.get("content-range") or "").endswith(f"/{CHUNK_BYTES * 3}"),
       r.headers.get("content-range"))

    # A mid-file seek is served from where it was asked for.
    async with Session() as db:
        r2 = await stream_video(big["slug"], FakeRequest({"range": "bytes=5000-5099"}), 0, db)
    ck("serving: a small explicit range is served exactly",
       r2.status_code == 206 and len(getattr(r2, "body", b"") or b"") == 100,
       f"status {r2.status_code}, {len(getattr(r2, 'body', b'') or b'')} bytes")

    # A download with no Range must be the COMPLETE file, not a first chunk.
    async with Session() as db:
        d = await stream_video(big["slug"], FakeRequest({}), 1, db)
    ck("serving: a download with no range streams the WHOLE file, not a chunk",
       d.__class__.__name__ == "FileResponse", d.__class__.__name__)
    ck("serving: the download is named for the upload",
       "big.mp4" in d.headers.get("content-disposition", ""),
       d.headers.get("content-disposition"))
    ck("serving: the whole-file path streams rather than buffering",
       not hasattr(d, "body") or not d.body)

    # HEAD. FastAPI does not add it to a GET route the way plain Starlette
    # does, so this 405'd — and players, download managers and uptime checks
    # all probe with HEAD before they stream.
    from app.routers.instructional_videos import public_router
    # The router's prefix is part of the registered path, so match on the end.
    file_route = next(r for r in public_router.routes
                      if getattr(r, "path", "").endswith("/{slug}/file"))
    ck("HEAD: the file endpoint accepts it", "HEAD" in file_route.methods,
       str(sorted(file_route.methods)))
    poster_route = next(r for r in public_router.routes
                        if getattr(r, "path", "").endswith("/{slug}/poster"))
    ck("HEAD: the poster endpoint accepts it too", "HEAD" in poster_route.methods,
       str(sorted(poster_route.methods)))

    async with Session() as db:
        h = await stream_video(big["slug"], FakeRequest({}, method="HEAD"), 0, db)
    ck("HEAD: answers 200", h.status_code == 200, str(h.status_code))
    ck("HEAD: reports the WHOLE file size, not a chunk",
       h.headers.get("content-length") == str(CHUNK_BYTES * 3), h.headers.get("content-length"))
    ck("HEAD: advertises range support", h.headers.get("accept-ranges") == "bytes")
    ck("HEAD: carries no body", not (getattr(h, "body", b"") or b""))
    ck("HEAD: never answers with a partial range",
       h.status_code != 206 and "content-range" not in {k.lower() for k in h.headers})

    # The nginx hand-off is opt-in. On by default is what 404'd in production,
    # because it needs the directory mounted into the frontend container too.
    from app.config.settings import settings as _settings
    ck("serving: the nginx hand-off is OFF unless explicitly configured",
       (_settings.video_accel_location or "") == "", _settings.video_accel_location)

    async with Session() as db:
        await svc.delete_video(db, big["id"])

    # Range maths, run through the route's own parser.
    from app.routers.instructional_videos import _parse_range
    ck("range: a plain range parses", _parse_range("bytes=0-99", 1000) == (0, 99))
    ck("range: an open-ended range runs to the end", _parse_range("bytes=500-", 1000) == (500, 999))
    ck("range: a suffix range reads the tail", _parse_range("bytes=-100", 1000) == (900, 999))
    ck("range: an end past the file is clamped", _parse_range("bytes=900-99999", 1000) == (900, 999))
    ck("range: a start past the file is refused", _parse_range("bytes=5000-", 1000) is None)
    ck("range: junk is ignored rather than erroring", _parse_range("cheese", 1000) is None)
    ck("range: no header means the whole file", _parse_range(None, 1000) is None)

    # Clear the two extra rows so the ordering checks below see three again.
    async with Session() as db:
        await svc.delete_video(db, orphan["id"])

    # -------------------------------------------------------------- ordering
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
        blob = await svc.video_file(db, dup["slug"])
        orphans = await svc.orphaned_files(db)
    ck("delete: THE FILE GOES WITH THE ENTRY, no orphan left behind",
       blob is None and orphans == [], str(orphans))
    async with Session() as db:
        ck("delete: an unknown id reports failure rather than raising",
           not await svc.delete_video(db, str(uuid.uuid4())))
        ck("delete: junk id reports failure", not await svc.delete_video(db, "not-a-uuid"))

    # ---------------------------------------------------- route-body guards
    from app.routers.instructional_videos import _poster_upload, _video_upload
    from fastapi import HTTPException

    def refuses_video(upload):
        try:
            _video_upload(upload)
            return None
        except HTTPException as e:
            return e.status_code

    async def refuses_poster(upload):
        try:
            await _poster_upload(upload)
            return None
        except HTTPException as e:
            return e.status_code

    ck("upload: an mp4 is accepted",
       _video_upload(FakeUpload("a.mp4", "video/mp4", b"x"))[1] == "video/mp4")
    ck("upload: a webm is accepted",
       _video_upload(FakeUpload("a.webm", "video/webm", b"x"))[1] == "video/webm")
    ck("upload: a .mov is refused with 415",
       refuses_video(FakeUpload("a.mov", "video/quicktime", b"x")) == 415)
    ck("upload: a mime with a charset suffix still matches",
       _video_upload(FakeUpload("a.mp4", "video/mp4; charset=binary", b"x"))[1] == "video/mp4")
    ck("upload: an oversized video is refused with 413",
       refuses_video(FakeUpload("big.mp4", "video/mp4", b"x" * (svc.MAX_VIDEO_BYTES + 1))) == 413)
    ck("upload: an oversized POSTER is refused with 413",
       await refuses_poster(
           FakeUpload("p.jpg", "image/jpeg", b"x" * (svc.MAX_POSTER_BYTES + 1))) == 413)
    ck("upload: a poster that is not an image is refused",
       await refuses_poster(FakeUpload("a.mp4", "video/mp4", b"x")) == 415)
    ck("upload: no file at all reads as nothing sent", _video_upload(None) is None)
    ck("upload: an empty file reads as nothing sent",
       _video_upload(FakeUpload("a.mp4", "video/mp4", b"")) is None)
    ck("upload: the size check does not consume the stream",
       _video_upload(FakeUpload("a.mp4", "video/mp4", b"abc"))[0].read() == b"abc")

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
            video_stream=stream(b"q" * 10), video_mime="video/mp4", video_filename="q.mp4",
            poster_bytes_data=None, poster_mime=None, created_by_user_id=user_id,
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

    # ------------------------------------------------------------- duration
    # The length used to be typed into the title by hand. It is a property of
    # the video, so it is stored as SECONDS and formatted in one place.
    async with Session() as db:
        timed = await svc.create_video(
            db, title="A timed walkthrough", description="", module_label=None,
            video_stream=stream(b"T" * 40), video_mime="video/mp4",
            video_filename="t.mp4", duration_seconds="165",
            poster_bytes_data=None, poster_mime=None, created_by_user_id=user_id,
        )
    ck("duration: stored as seconds", timed["duration_seconds"] == 165,
       str(timed["duration_seconds"]))
    ck("duration: formatted for a reader", timed["duration"] == "2m 45s", str(timed["duration"]))
    ck("duration: ISO-8601 for the VideoObject", timed["duration_iso"] == "PT2M45S",
       str(timed["duration_iso"]))

    async with Session() as db:
        untimed = await svc.create_video(
            db, title="An untimed walkthrough", description="", module_label=None,
            video_stream=stream(b"U" * 40), video_mime="video/mp4",
            video_filename="u.mp4", poster_bytes_data=None, poster_mime=None,
            created_by_user_id=user_id,
        )
    ck("duration: a video with no length reports none, not a zero",
       untimed["duration_seconds"] is None and untimed["duration"] is None
       and untimed["duration_iso"] is None)

    # A field left out of the form must not blank a length already recorded —
    # the same rule every other field on this record follows.
    async with Session() as db:
        kept = await svc.update_video(db, timed["id"], fields={"title": "Renamed, same length"})
    ck("duration: an edit that does not mention it leaves it alone",
       kept["duration_seconds"] == 165, str(kept["duration_seconds"]))

    async with Session() as db:
        recut = await svc.update_video(db, timed["id"], fields={"duration_seconds": "1:02:45"})
    ck("duration: a clock string is refused rather than half-read",
       recut["duration_seconds"] is None, str(recut["duration_seconds"]))

    async with Session() as db:
        fixed = await svc.update_video(db, timed["id"], fields={"duration_seconds": 3765})
    ck("duration: an hour-long video formats with its minutes",
       fixed["duration"] == "1h 2m 45s" and fixed["duration_iso"] == "PT1H2M45S",
       f"{fixed['duration']} / {fixed['duration_iso']}")

    async with Session() as db:
        cleared = await svc.update_video(db, timed["id"], fields={"duration_seconds": ""})
    ck("duration: an emptied field clears the value", cleared["duration_seconds"] is None)

    for junk in ("abc", "-5", "0", 86401):
        async with Session() as db:
            bad = await svc.update_video(db, timed["id"], fields={"duration_seconds": junk})
        ck(f"duration: {junk!r} reads as not set rather than being stored",
           bad["duration_seconds"] is None, str(bad["duration_seconds"]))

    async with Session() as db:
        for gone in (timed["id"], untimed["id"]):
            await svc.delete_video(db, gone)

    # ------------------------------------------------------------- downgrade
    async with engine.begin() as conn:
        for stmt in DURATION_DOWNGRADE + DOWNGRADE_STATEMENTS:
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
