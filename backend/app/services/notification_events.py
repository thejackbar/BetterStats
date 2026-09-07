"""The catalogue of things a club can be told about.

**THE CATALOGUE IS CODE, NOT DATA, and that is deliberate.** Every event here
needs a source function that knows how to find it, so a row in a table
describing an event nothing can produce would be a promise the platform cannot
keep. Adding an event means adding an ``EventType`` here AND a source in
``services/notification_scan.py``; the settings screen is drawn from this list,
so nothing else needs editing.

What a club's own settings may change is on top of these defaults:

  - whether the event fires at all (``club_notification_rules.enabled``),
  - which channels it uses (email today, the in-app bell, and whatever is added
    later — a channel is a string, not a column),
  - the event's own numbers (``config``), which is where the notice period
    before a Working With Children check lapses lives.

**A DEFAULT IS THE CLUB'S UNTIL THEY SAY OTHERWISE.** A club with no rule row
behaves exactly as declared here, so changing a default changes it for every
club that has never opened the screen and for none that has. That is why
``default_enabled`` is conservative for the noisy events (a successful sync is
worth a line in the bell and is not worth an email).

**CAPABILITY IS A FILTER ON WHO IS TOLD, NEVER ON WHO MAY CONFIGURE.** A
notification about a saved report awaiting approval goes to the people who can
approve one, the same rule the notification bell already applies — telling
everybody about a queue they cannot act on is noise. ``capability=None`` means
every club admin.

**MODULE IS AN ENTITLEMENT GATE.** An event whose subject matter belongs to a
paid module is neither emitted nor offered to a club that does not hold it, so a
club never configures a notification it can never receive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.auth.capabilities import (
    MANAGE_ASSETS, MANAGE_MERCH, MANAGE_QUALIFICATIONS, MANAGE_REPORTS,
)

#: Channels a notification can travel on. Email is the one that leaves the
#: building; in_app is the bell. Adding SMS or push later means adding a value
#: here plus a sender — no schema change, because a channel is stored as text.
CHANNEL_EMAIL = "email"
CHANNEL_IN_APP = "in_app"
CHANNELS = (CHANNEL_EMAIL, CHANNEL_IN_APP)

CHANNEL_LABELS = {
    CHANNEL_EMAIL: "Email",
    CHANNEL_IN_APP: "In the app",
}

#: The whole-club opt-out, stored as a ``user_notification_preferences`` row
#: whose event_key is this sentinel. A real event key alongside it narrows the
#: opt-out to that event; this one covers everything the club can send.
ALL_EVENTS = "*"

#: Severities, worst last. Drives the colour on the bell and nothing else — a
#: warning is not sent any differently from an info.
SEVERITIES = ("info", "warning", "urgent")


@dataclass(frozen=True)
class ConfigField:
    """One number a club may set on an event.

    ``minimum``/``maximum`` are enforced server-side on save, so a value typed
    into a browser can never put a source into a state it cannot answer (a
    negative notice period would look backwards through time).
    """
    key: str
    label: str
    hint: str
    default: int
    minimum: int
    maximum: int
    unit: str = "days"


@dataclass(frozen=True)
class EventType:
    key: str
    label: str
    description: str
    #: Which section of the settings screen it is drawn under.
    category: str
    severity: str = "info"
    default_enabled: bool = True
    #: Per-channel default. A channel missing from this map defaults to OFF, so
    #: a channel added later is opt-in rather than switching itself on for every
    #: club overnight.
    default_channels: dict = field(default_factory=lambda: {CHANNEL_EMAIL: True, CHANNEL_IN_APP: True})
    #: Entitlement gate. None = core, every club.
    module: Optional[str] = None
    #: Who is told. None = every club admin.
    capability: Optional[str] = None
    config_fields: tuple[ConfigField, ...] = ()

    def default_config(self) -> dict:
        return {f.key: f.default for f in self.config_fields}


CATEGORIES = (
    ("stats", "Stats and milestones"),
    ("people", "People and compliance"),
    ("operations", "Club operations"),
    ("data", "Data and sync"),
)


EVENT_TYPES: tuple[EventType, ...] = (
    # ── Stats ────────────────────────────────────────────────────────────────
    EventType(
        key="milestone_achieved",
        label="A milestone was reached",
        description=(
            "A player has passed a career milestone — 1,000 runs, 100 wickets, "
            "50 matches, and so on. Sent once per milestone, when the scorecard "
            "carrying it lands."
        ),
        category="stats",
    ),
    EventType(
        key="milestone_upcoming",
        label="A milestone is coming up",
        description=(
            "A player is within reach of their next career milestone, so the club "
            "can mark the occasion. Announced once per milestone, not every week "
            "until they get there."
        ),
        category="stats",
    ),
    # ── People and compliance ───────────────────────────────────────────────
    EventType(
        key="qualification_expiring",
        label="A certification is about to lapse",
        description=(
            "A volunteer's or official's Working With Children check, RSA, first "
            "aid certificate or coaching accreditation is close to its expiry "
            "date — or has already passed it. One notice per certificate, so a "
            "renewal is chased rather than nagged."
        ),
        category="people",
        severity="warning",
        capability=MANAGE_QUALIFICATIONS,
        config_fields=(
            ConfigField(
                key="lead_days",
                label="Notice period",
                hint=(
                    "How long before the expiry date to raise it. A Working With "
                    "Children renewal takes weeks to come back, so the default is "
                    "deliberately generous."
                ),
                default=60, minimum=1, maximum=365,
            ),
        ),
    ),
    # ── Club operations ──────────────────────────────────────────────────────
    EventType(
        key="asset_service_due",
        label="Gear or a facility is due for service",
        description=(
            "Something on the club's asset register is due for a service or "
            "replacement inside the notice period."
        ),
        category="operations",
        severity="warning",
        capability=MANAGE_ASSETS,
        config_fields=(
            ConfigField(
                key="lead_days",
                label="Notice period",
                hint="How far ahead of the due date to raise it.",
                default=30, minimum=1, maximum=365,
            ),
        ),
    ),
    EventType(
        key="merch_low_stock",
        label="Stock is running low",
        description="A product has fallen to or below the low-stock level set for it.",
        category="operations",
        severity="warning",
        module="merch",
        capability=MANAGE_MERCH,
    ),
    EventType(
        key="report_pending",
        label="A saved report is waiting for approval",
        description="A member has shared a StatLab report with the club and it needs a look before it goes live.",
        category="operations",
        capability=MANAGE_REPORTS,
    ),
    # ── Data and sync ────────────────────────────────────────────────────────
    EventType(
        key="sync_failed",
        label="A data sync failed",
        description="Pulling results from Cricket Australia did not finish. Worth knowing quickly — the club's stats stop moving until it does.",
        category="data",
        severity="urgent",
    ),
    EventType(
        key="sync_completed",
        label="New results have landed",
        description="A sync finished and brought new matches in.",
        category="data",
        # In the bell, not in the inbox. A club that wants the weekly "results
        # are in" email can switch it on; sending it to everybody by default is
        # how a notification system trains people to ignore it.
        default_channels={CHANNEL_EMAIL: False, CHANNEL_IN_APP: True},
    ),
    EventType(
        key="player_request_pending",
        label="A player has asked for their stats to be checked",
        description="Someone has raised a request against their own record from the public site.",
        category="data",
    ),
)

EVENTS_BY_KEY: dict[str, EventType] = {e.key: e for e in EVENT_TYPES}


def get_event(key: str) -> Optional[EventType]:
    return EVENTS_BY_KEY.get(key)


def clean_config(event: EventType, raw: dict | None, base: dict | None = None) -> dict:
    """A club's config for one event, with every value checked and anything the
    event does not declare dropped.

    An out-of-range number is CLAMPED to the declared bounds rather than
    refused: the alternative is a source silently reading a lead time of -5 and
    looking backwards through time, which is a wrong notification rather than a
    missing setting.

    ``base`` is what an unreadable value falls back to. **A save passes the
    club's CURRENT config**, so typing nonsense into the notice period leaves
    what the club had set alone; a READ passes nothing, so a stored value that
    has somehow gone bad falls back to the registry default, which is the only
    other thing that could be meant. Getting this the wrong way round quietly
    resets a club's own setting on the next save — found by running it.
    """
    out = event.default_config()
    if isinstance(base, dict):
        for f in event.config_fields:
            if f.key in base:
                try:
                    out[f.key] = max(f.minimum, min(f.maximum, int(base[f.key])))
                except (TypeError, ValueError):
                    pass
    if not isinstance(raw, dict):
        return out
    for f in event.config_fields:
        if f.key not in raw:
            continue
        try:
            value = int(raw[f.key])
        except (TypeError, ValueError):
            continue
        out[f.key] = max(f.minimum, min(f.maximum, value))
    return out


def clean_channels(raw: dict | None) -> dict:
    """A channel map off the wire, reduced to the channels that exist.

    Only a channel PRESENT in the payload is recorded, so a partial save leaves
    the others to fall back to their default rather than silently switching them
    off — the same present-means-intent rule ``patch_member_season`` keeps.
    """
    if not isinstance(raw, dict):
        return {}
    return {c: bool(raw[c]) for c in CHANNELS if c in raw}
