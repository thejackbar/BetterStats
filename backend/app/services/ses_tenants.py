"""Amazon SES per-club tenants (multi-tenancy provisioning).

Each club is its own SES **tenant** so its sending reputation is isolated and can
be paused independently of every other club. Tenants are auto-provisioned here:
on club onboarding, and via a backfill over all clubs. The everyday send
credential (``ses_access_key_id``) stays send-only; provisioning uses a SEPARATE
admin credential (``ses_provision_*``) that can create tenants and associate
resources.

Provisioning is idempotent and best-effort — a failure never blocks onboarding
or a send; the club just stays unprovisioned (nullable columns) and the next
backfill retries. ``ensure_tenant``:

  1. CreateTenant (deterministic slugified name; an existing tenant is fine),
  2. associate the shared sending identity for the club's silo,
  3. associate the club's context configuration set (clubs → transactional,
     the outreach org → campaigns),
  4. store the tenant name / id on the org.

Reputation policy is left to the SES default assigned at tenant creation unless
``ses_reputation_policy`` names one (association TODO — verify the API first).

SESv2 REST, SigV4-signed, stdlib signer (matches services/email_service, no
boto3). The two calls used are POST; both are treated as idempotent by catching
"already exists"/"already associated". **First-run note:** verify the tenant
endpoint paths + the send-time attribution against current SES docs before
enabling ``ses_tenant_sends_enabled``.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import json
import logging
import re

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import Organisation
from app.services.marketing_org import org_is_outreach

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_CREATE_TENANT_PATH = "/v2/email/tenants"
_ASSOC_PATH = "/v2/email/tenants/resources"


# ─── config: what identity / config set a club's tenant is wired to ──────────

def config_set_for(org: Organisation) -> str:
    """The configuration set a club sends on: the outreach org uses the campaign
    stream; a normal club uses the transactional stream (both carry an SNS event
    destination). This is the single source of truth, shared by the send path."""
    if org_is_outreach(org):
        return (settings.ses_configuration_set or "").strip()
    return (settings.ses_configuration_set_transactional or "").strip()


def _sending_domain(org: Organisation) -> str:
    return (settings.ses_marketing_domain if org_is_outreach(org)
            else settings.ses_club_domain)


def tenant_name_for(org: Organisation) -> str:
    """Deterministic tenant name for a club: the outreach org maps to the fixed
    marketing tenant; every club maps to the slugified club name."""
    if org_is_outreach(org):
        return (settings.ses_marketing_tenant_name or "bettercricket-marketing").strip()
    slug = _slugify(org.name or "") or _slugify(str(org.slug or "")) or f"club-{str(org.id)[:8]}"
    return slug[:64]


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return s


def _identity_arn(org: Organisation) -> str:
    return f"arn:aws:ses:{settings.ses_region}:{settings.ses_account_id}:identity/{_sending_domain(org)}"


def _config_set_arn(org: Organisation) -> str:
    return (f"arn:aws:ses:{settings.ses_region}:{settings.ses_account_id}:"
            f"configuration-set/{config_set_for(org)}")


def provisioning_configured() -> bool:
    return bool(
        (settings.email_provider or "").strip().lower() == "ses"
        and (settings.ses_account_id or "").strip()
        and (settings.ses_provision_access_key_id or "").strip()
        and (settings.ses_provision_secret_access_key or "").strip()
    )


# ─── SigV4 (POST, JSON) — stdlib, provisioning credentials ───────────────────

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sigv4_headers(*, path: str, body: str) -> dict:
    region = settings.ses_region
    host = f"email.{region}.amazonaws.com"
    access_key = settings.ses_provision_access_key_id
    secret_key = settings.ses_provision_secret_access_key
    content_type = "application/json"
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    canonical_headers = (
        f"content-type:{content_type}\nhost:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n")
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(["POST", path, "", canonical_headers, signed_headers, payload_hash])
    scope = f"{date_stamp}/{region}/ses/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()])
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, "ses")
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Content-Type": content_type,
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                          f"SignedHeaders={signed_headers}, Signature={signature}"),
    }


_MAX_RETRIES = 4


def _is_throttle(status: int, data: dict) -> bool:
    if status == 429 or status >= 500:
        return True
    blob = json.dumps(data).lower()
    return "throttl" in blob or "toomanyrequests" in blob or "limitexceeded" in blob and "rate" in blob


async def _post(path: str, payload: dict) -> tuple[int, dict]:
    """POST to the SES management API, retrying throttles / 5xx with backoff. SES
    tenant operations rate-limit aggressively, so a bulk backfill needs this."""
    body = json.dumps(payload)
    host = f"email.{settings.ses_region}.amazonaws.com"
    status, data = 0, {}
    for attempt in range(_MAX_RETRIES + 1):
        headers = _sigv4_headers(path=path, body=body)  # re-sign (time-bound) each try
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(f"https://{host}{path}", content=body, headers=headers)
            status = resp.status_code
            data = {}
            if resp.content:
                try:
                    data = resp.json()
                except Exception:  # noqa: BLE001
                    data = {"_raw": resp.text[:500]}
        except Exception as e:  # noqa: BLE001 — network/timeout
            status, data = 0, {"_error": str(e)}
        if attempt < _MAX_RETRIES and _is_throttle(status, data):
            await asyncio.sleep(min(0.5 * (2 ** attempt), 8.0))
            continue
        break
    return status, data


def _is_already_exists(status: int, data: dict) -> bool:
    """SES returns a 4xx with an already-exists-type message when the tenant or
    association is already there — which for an idempotent ensure is success.
    AWS phrases it "... already exists" (with a space), so match that too."""
    if status < 400:
        return True
    blob = json.dumps(data).lower()
    return ("already exist" in blob or "alreadyexist" in blob
            or "already associated" in blob or "conflict" in blob)


# ─── provisioning ────────────────────────────────────────────────────────────

async def ensure_tenant(session: AsyncSession, org: Organisation) -> dict:
    """Idempotently ensure the club's SES tenant exists and is wired to the shared
    identity + its context config set; store the tenant name/id on the org.
    Best-effort: returns a status dict and never raises into the caller."""
    if not provisioning_configured():
        return {"skipped": "ses tenant provisioning not configured"}
    name = tenant_name_for(org)
    try:
        # 1. Create the tenant (existing is fine).
        status, data = await _post(_CREATE_TENANT_PATH, {"TenantName": name})
        if not _is_already_exists(status, data):
            logger.warning("SES CreateTenant %s failed: %s %s", name, status, data)
            return {"error": f"create_tenant {status}", "detail": data, "tenant": name}
        tenant_id = data.get("TenantId") or org.ses_tenant_id

        # 2. Associate the shared sending identity + the context config set.
        for arn in (_identity_arn(org), _config_set_arn(org)):
            a_status, a_data = await _post(_ASSOC_PATH, {"TenantName": name, "ResourceArn": arn})
            if not _is_already_exists(a_status, a_data):
                logger.warning("SES associate %s → %s failed: %s %s", name, arn, a_status, a_data)

        # 3. Persist onto the org.
        org.ses_tenant_name = name
        if tenant_id:
            org.ses_tenant_id = tenant_id
        org.ses_tenant_provisioned_at = datetime.datetime.now(datetime.timezone.utc)
        await session.commit()
        return {"ok": True, "tenant": name, "tenant_id": tenant_id,
                "identity": _sending_domain(org), "config_set": config_set_for(org)}
    except Exception as e:  # noqa: BLE001 — provisioning never blocks the caller
        logger.error("ensure_tenant failed for %s: %s", org.id, e, exc_info=True)
        try:
            await session.rollback()
        except Exception:
            pass
        return {"error": str(e), "tenant": name}


async def ensure_tenant_bg(org_id) -> None:
    """Detached best-effort provisioning (onboarding hook) — own session."""
    if not provisioning_configured():
        return
    from app.models.db import async_session_maker
    try:
        async with async_session_maker() as session:
            org = await session.get(Organisation, org_id)
            if org is not None:
                await ensure_tenant(session, org)
    except Exception as e:  # noqa: BLE001
        logger.error("ensure_tenant_bg failed for %s: %s", org_id, e, exc_info=True)


async def set_tenant_paused(session: AsyncSession, tenant_name: str, paused: bool) -> bool:
    """Reflect an SES tenant status change (paused/resumed) onto the owning club.
    Returns True if a club matched. Called from the SES event webhook."""
    name = (tenant_name or "").strip()
    if not name:
        return False
    org = (await session.execute(
        select(Organisation).where(Organisation.ses_tenant_name == name))).scalars().first()
    if org is None:
        return False
    org.ses_tenant_paused = bool(paused)
    await session.commit()
    logger.info("SES tenant %s %s (club %s)", name, "paused" if paused else "resumed", org.id)
    return True


async def provision_all(session: AsyncSession, *, only_unprovisioned: bool = True) -> dict:
    """Backfill: ensure a tenant for every org. ``only_unprovisioned`` skips orgs
    already provisioned (re-run safe / cheap); pass False to re-associate all."""
    if not provisioning_configured():
        return {"skipped": "ses tenant provisioning not configured"}
    stmt = select(Organisation)
    if only_unprovisioned:
        stmt = stmt.where(Organisation.ses_tenant_provisioned_at.is_(None))
    orgs = (await session.execute(stmt)).scalars().all()
    done = failed = 0
    errors: list[dict] = []
    for i, org in enumerate(orgs):
        res = await ensure_tenant(session, org)
        if res.get("ok"):
            done += 1
        elif "skipped" not in res:
            failed += 1
            if len(errors) < 20:  # surface the first few reasons for the UI
                errors.append({"club": org.name, "tenant": res.get("tenant"),
                               "reason": res.get("error"), "detail": res.get("detail")})
        # Pace the loop so a large backfill doesn't trip the SES management
        # rate limit (each org is up to 3 API calls).
        if i + 1 < len(orgs):
            await asyncio.sleep(0.4)
    result = {"provisioned": done, "failed": failed, "total": len(orgs), "errors": errors}
    logger.info("SES provision_all: provisioned=%d failed=%d total=%d", done, failed, len(orgs))
    return result
