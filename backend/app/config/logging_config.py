"""One place that decides what the backend actually writes to the log.

The container log used to be dominated by success notifications rather than
anything anyone would act on. Two sources, both third-party, both one line per
operation:

  * **httpx** logs an INFO line for every outbound request it makes. A single
    sync pass fetches thousands of Grassroots scorecards, so a routine sync
    buried every real warning under thousands of ``HTTP Request: GET … "200
    OK"`` lines.
  * **uvicorn's access log** logs an INFO line for every request served,
    including the notification-bell poll every client runs on a 60s timer.

Neither says anything a healthy backend needs to say. Our own code's INFO
messages (sync progress, scheduler jobs, seeded rows) are a few dozen lines per
run and are kept — they're the ones that explain what a long job is doing.

Everything here is env-overridable so a specific problem can be debugged
without a code change:

  ``LOG_LEVEL``              our own code's floor. Default INFO.
  ``THIRD_PARTY_LOG_LEVEL``  the libraries listed below. Default WARNING;
                             set INFO to get httpx's per-request lines back.
  ``ACCESS_LOG``             ``errors`` (default — only 4xx/5xx are logged),
                             ``all`` (every request, uvicorn's own behaviour)
                             or ``off``.
"""
import logging
import os

# Libraries that log routine success at INFO. httpx/httpcore are the loud ones
# here (one line per upstream call); the rest are included so a future
# dependency bump can't quietly reintroduce the same problem.
_THIRD_PARTY_LOGGERS = (
    "httpx",
    "httpcore",
    "hpack",
    "h11",
    "urllib3",
    "asyncio",
    "botocore",
    "boto3",
    "s3transfer",
    "anthropic",
    "stripe",
    "apscheduler",
    "PIL",
    "multipart",
    "python_multipart",
    "watchfiles",
    "charset_normalizer",
)

_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"


class SuppressSuccessfulRequests(logging.Filter):
    """Drop uvicorn access-log records for responses that succeeded.

    uvicorn formats an access record as ``'%s - "%s %s HTTP/%s" %d'`` with the
    status code as the fifth arg, so the status is readable without parsing the
    rendered message. A record we can't read a status out of is kept — a filter
    that guesses wrong should err towards logging, not towards silence.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 5:
            status = args[4]
            try:
                return int(status) >= 400
            except (TypeError, ValueError):
                return True
        return True


def _level(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip().upper()
    if not raw:
        return default
    resolved = logging.getLevelName(raw)
    # getLevelName returns the string "Level FOO" for anything unrecognised.
    return resolved if isinstance(resolved, int) else default


def configure_logging() -> None:
    """Apply the logging policy above. Safe to call more than once.

    Call this at import time of an entrypoint module. uvicorn runs its own
    ``dictConfig`` while building its Config, which happens *before* it imports
    the app, so configuring here lands after uvicorn and wins.
    """
    app_level = _level("LOG_LEVEL", logging.INFO)
    third_party_level = _level("THIRD_PARTY_LOG_LEVEL", logging.WARNING)

    logging.basicConfig(level=app_level, format=_FORMAT, force=True)
    logging.getLogger().setLevel(app_level)

    for name in _THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(third_party_level)

    access_mode = (os.getenv("ACCESS_LOG", "errors").strip().lower() or "errors")
    access = logging.getLogger("uvicorn.access")
    access.filters = [f for f in access.filters
                      if not isinstance(f, SuppressSuccessfulRequests)]
    if access_mode == "off":
        access.disabled = True
    elif access_mode == "all":
        access.disabled = False
    else:
        access.disabled = False
        access.addFilter(SuppressSuccessfulRequests())
