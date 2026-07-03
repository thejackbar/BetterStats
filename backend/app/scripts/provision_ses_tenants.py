"""Backfill SES per-club tenants.

Ensures an Amazon SES tenant for every club (create + associate the shared
identity and the club's context configuration set), storing the tenant on each
org. Idempotent and best-effort — safe to re-run.

    python -m app.scripts.provision_ses_tenants          # only clubs not yet provisioned
    python -m app.scripts.provision_ses_tenants --all    # re-associate resources for every club

Requires the provisioning credentials in the environment (ses_provision_* +
ses_account_id). No-op with a clear message when they're unset.
"""
import asyncio
import sys

from app.models.db import async_session_maker
from app.services import ses_tenants


async def _run(only_unprovisioned: bool) -> None:
    if not ses_tenants.provisioning_configured():
        print("SES tenant provisioning is not configured (set ses_account_id + "
              "ses_provision_access_key_id + ses_provision_secret_access_key, "
              "email_provider=ses).")
        return
    async with async_session_maker() as session:
        result = await ses_tenants.provision_all(session, only_unprovisioned=only_unprovisioned)
    print(result)


if __name__ == "__main__":
    only_unprovisioned = "--all" not in sys.argv[1:]
    asyncio.run(_run(only_unprovisioned))
