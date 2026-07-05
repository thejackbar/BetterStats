"""Independently audit how much the account has sent through Amazon SES.

Answers "how many emails has SES actually accepted from us in the last 24h?"
from **AWS's own counter**, not our database — so you can cross-check the
BetterComms summary stats against the source of truth. Uses the SESv2
``GetAccount`` API (a signed GET to ``/v2/email/account``), which returns
``SendQuota.SentLast24Hours`` — AWS's rolling-24-hour tally across the whole
account (every club + BetterCricket's own campaigns combined).

It signs with the SES send credentials already in the server ``.env``
(``SES_ACCESS_KEY_ID`` / ``SES_SECRET_ACCESS_KEY`` / ``SES_REGION``) — no AWS
CLI, no boto3, stdlib SigV4 (same approach as services/email_service). It also
prints our own database's count of sends in the same window so you can see both
numbers next to each other.

Run it on the box (via docker compose, project name pinned per the deploy rules):

  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec betterstats-backend python -m app.scripts.ses_quota

Read-only. Sends nothing. Note SentLast24Hours is a ROLLING 24-hour window (how
SES enforces the daily quota), not a calendar day — for a calendar-day breakdown
use CloudWatch's SES "Send" metric or the SES console Account dashboard.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import json
import urllib.request
import urllib.error

from app.config.settings import settings


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_account() -> dict:
    """Signed SESv2 GetAccount (GET /v2/email/account). Returns the parsed JSON."""
    region = settings.ses_region
    access_key = settings.ses_access_key_id
    secret_key = settings.ses_secret_access_key
    if not (access_key and secret_key):
        raise RuntimeError(
            "SES credentials are not configured (SES_ACCESS_KEY_ID / "
            "SES_SECRET_ACCESS_KEY). Set them in the server .env.")
    host = f"email.{region}.amazonaws.com"
    path = "/v2/email/account"
    service = "ses"

    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(b"").hexdigest()   # GET → empty body

    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([
        "GET", path, "", canonical_headers, signed_headers, payload_hash,
    ])
    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    req = urllib.request.Request(
        f"https://{host}{path}",
        headers={
            "Host": host,
            "X-Amz-Date": amz_date,
            "X-Amz-Content-Sha256": payload_hash,
            "Authorization": authorization,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"SES GetAccount failed: HTTP {e.code} — {body}") from None


async def _db_sent_last_24h() -> "int | None":
    """Our own tally: comms_recipients marked sent in the last 24h (account-wide).
    Returns None if the DB can't be reached."""
    try:
        from sqlalchemy import select, func
        from app.models.db import async_session_maker, CommsRecipient
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
        async with async_session_maker() as s:
            return int((await s.scalar(
                select(func.count(CommsRecipient.id)).where(
                    CommsRecipient.status == "sent",
                    CommsRecipient.sent_at >= since))) or 0)
    except Exception as e:  # pragma: no cover - diagnostics only
        print(f"  (couldn't read our own DB count: {e})")
        return None


def _fmt(n) -> str:
    try:
        return f"{int(float(n)):,}"
    except (TypeError, ValueError):
        return str(n)


async def _main() -> None:
    acct = _get_account()
    quota = acct.get("SendQuota") or {}
    print("Amazon SES — account (the source of truth):")
    print(f"  Sent in last 24h (SES)     : {_fmt(quota.get('SentLast24Hours'))}")
    print(f"  Max per 24h  (SES grant)   : {_fmt(quota.get('Max24HourSend'))}")
    print(f"  Max send rate/sec (SES)    : {quota.get('MaxSendRate')}")
    print(f"  Sending enabled            : {acct.get('SendingEnabled')}")
    print(f"  Production access          : {acct.get('ProductionAccessEnabled')}")
    print(f"  Enforcement status         : {acct.get('EnforcementStatus')}")
    print()
    print("Our side, for comparison:")
    print(f"  Practical daily limit (env): {_fmt(settings.ses_daily_send_limit)}"
          f"   (super-admin value may override this in the DB)")
    print(f"  Our pacing rate/sec (env)  : {settings.ses_max_send_rate}")
    ours = await _db_sent_last_24h()
    if ours is not None:
        print(f"  BetterComms sent (last 24h): {_fmt(ours)}   (comms_recipients status=sent)")
    print()
    print("Note: SES 'SentLast24Hours' is a rolling 24-hour window, not a calendar")
    print("day. For a calendar-day view use the SES console Account dashboard or the")
    print("CloudWatch 'Send' metric.")


if __name__ == "__main__":
    asyncio.run(_main())
