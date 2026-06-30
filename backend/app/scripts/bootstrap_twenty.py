"""Bootstrap the Twenty CRM data model for the BetterCricket integration.

Idempotent. Creates the custom objects (Association, Touchpoint, Email), the
custom fields on Companies / People / Opportunities and those new objects, and
rewrites the Opportunity pipeline stages to the BetterCricket sales pipeline.
Re-running skips anything that already exists, so it is safe to run repeatedly
as the model evolves.

Reads two env vars (set them in the server .env, never commit the key):
    TWENTY_API_URL   e.g. https://twenty.betterat.cricket   (the SERVER_URL)
    TWENTY_API_KEY   a workspace API key with metadata write

Usage:
    TWENTY_API_URL=https://twenty.betterat.cricket TWENTY_API_KEY=... \
        python -m app.scripts.bootstrap_twenty

Relations between objects (Company<->Association many-to-many, Touchpoint ->
Company/Person/Email) are created in a second pass; see RELATIONS below. The
metadata relation payload is version-sensitive, so relations are attempted last
and a failure there does not abort the scalar-field pass.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("TWENTY_API_URL", "https://twenty.betterat.cricket").rstrip("/")
KEY = os.environ.get("TWENTY_API_KEY", "")

PALETTE = ["blue", "green", "turquoise", "sky", "purple", "pink", "yellow",
           "orange", "red", "gray"]


def _api(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def _value(label: str) -> str:
    """Twenty SELECT option values are identifier-ish; mirror the built-in style
    (e.g. 'NEW')."""
    return re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_")


def _options(labels):
    return [{"label": l, "value": _value(l), "color": PALETTE[i % len(PALETTE)],
             "position": i} for i, l in enumerate(labels)]


MODULES = ["BetterSelect", "BetterSocials", "BetterFees", "BetterComms",
           "BetterMerch", "BetterIQ", "BetterFantasyCricket"]
# value/label: keep the value as the canonical module key the backend uses.
MODULE_OPTS = [
    {"label": "BetterSelect", "value": "SELECT", "color": "purple", "position": 0},
    {"label": "BetterSocials", "value": "SOCIALS", "color": "yellow", "position": 1},
    {"label": "BetterFees", "value": "FEES", "color": "green", "position": 2},
    {"label": "BetterComms", "value": "COMMS", "color": "sky", "position": 3},
    {"label": "BetterMerch", "value": "MERCH", "color": "orange", "position": 4},
    {"label": "BetterIQ", "value": "IQ", "color": "blue", "position": 5},
    {"label": "BetterFantasyCricket", "value": "FANTASY", "color": "pink", "position": 6},
]

OBJECTS = [
    dict(nameSingular="association", namePlural="associations", labelSingular="Association",
         labelPlural="Associations", icon="IconTournament",
         description="A cricket association/competition a club belongs to"),
    dict(nameSingular="touchpoint", namePlural="touchpoints", labelSingular="Touchpoint",
         labelPlural="Touchpoints", icon="IconActivity",
         description="A typed correspondence/action/event with a club or officer"),
    dict(nameSingular="bcEmail", namePlural="bcEmails", labelSingular="Email",
         labelPlural="Emails", icon="IconMail",
         description="A named BetterComms bulk email (campaign)"),
    # Junction for the many-to-many between clubs and associations (Twenty's
    # metadata API has no native many-to-many). One row per club-in-association.
    dict(nameSingular="clubAssociation", namePlural="clubAssociations",
         labelSingular="Membership", labelPlural="Memberships", icon="IconUsersGroup",
         description="A club's membership of an association (club <-> association link)"),
    # Junction for the many-to-many between people and clubs. Twenty enforces one
    # Person per email, so a shared officer (same email across clubs) is one Person;
    # this junction is how they show under EVERY club they serve, each row carrying
    # that officer's role at that club. One row per club-officer post.
    dict(nameSingular="personClub", namePlural="personClubs",
         labelSingular="Officer role", labelPlural="Officer roles", icon="IconUserCheck",
         description="An officer's role at a club (person <-> club link)"),
]

# (object nameSingular, field name, label, type, options-or-None)
FIELDS = [
    # ---- Company ----
    ("company", "bcClubId", "BC Club Id", "TEXT", None),
    ("company", "bcOrgId", "BC Org Id", "TEXT", None),
    ("company", "lifecycleStage", "Lifecycle stage", "SELECT",
     _options(["Target", "Prospect", "Engaged", "Trial", "Customer", "Churned", "Suppressed"])),
    ("company", "subscriptionStatus", "Subscription status", "SELECT",
     _options(["None", "Trial", "Active", "Past due", "Paused", "Cancelled"])),
    ("company", "paidModules", "Paid modules", "MULTI_SELECT", MODULE_OPTS),
    ("company", "trialModules", "Trial modules", "MULTI_SELECT", MODULE_OPTS),
    ("company", "interestedModules", "Interested modules", "MULTI_SELECT", MODULE_OPTS),
    ("company", "engagementScore", "Engagement score", "NUMBER", None),
    ("company", "engagementTier", "Engagement tier", "SELECT",
     _options(["Cold", "Warm", "Hot"])),
    ("company", "lastSeenAt", "Last seen at", "DATE_TIME", None),
    ("company", "sessions30d", "Sessions (30d)", "NUMBER", None),
    ("company", "emailEngaged30d", "Email opens/clicks (30d)", "NUMBER", None),
    ("company", "lastEmailAt", "Last email engagement", "DATE_TIME", None),
    # Modules the club wants but isn't paying for — a prospect's interest or a
    # customer's expansion/trial-extra. Drives the in-sales-cycle flag.
    ("company", "upsellModules", "Upsell modules", "MULTI_SELECT", MODULE_OPTS),
    ("company", "inSalesCycle", "In sales cycle", "BOOLEAN", None),
    ("company", "renewalDate", "Renewal date", "DATE_TIME", None),
    ("company", "billingCycle", "Billing cycle", "SELECT", _options(["Monthly", "Annual"])),
    ("company", "arr", "ARR", "CURRENCY", None),
    # primaryAssociation (TEXT) dropped — the clubAssociation junction's isPrimary
    # flag carries this, so the denormalised field was redundant. Delete the old
    # field in Twenty (Settings > Data model > Company) to tidy up; harmless if left.
    ("company", "clubKind", "Club kind", "SELECT",
     _options(["Club", "Association", "Carnival", "School", "Junior"])),
    ("company", "postcode", "Postcode", "TEXT", None),
    ("company", "clubState", "State", "TEXT", None),
    ("company", "country", "Country", "TEXT", None),
    ("company", "dataSource", "Data source", "SELECT", _options(["PlayHQ", "Play-Cricket"])),
    ("company", "utmCode", "UTM code", "TEXT", None),
    ("company", "firstTouchSource", "First-touch source", "SELECT",
     _options(["Facebook", "Instagram", "Google", "Bing", "Email", "PlayHQ",
               "Play-Cricket", "Direct", "Referral", "Other"])),
    ("company", "existingKpCustomer", "Existing KP customer", "SELECT",
     _options(["No", "Yes", "Previous"])),
    ("company", "publicProfileUrl", "Public profile URL", "LINKS", None),
    ("company", "lastSyncedAt", "Last synced at", "DATE_TIME", None),
    # ---- Person ----
    ("person", "bcContactId", "BC Contact Id", "TEXT", None),
    ("person", "clubRole", "Club role", "SELECT",
     _options(["President", "Vice President", "Secretary", "Treasurer", "Registrar",
               "Coordinator", "Club contact", "Sponsor", "Other"])),
    ("person", "roleRank", "Role rank", "NUMBER", None),
    ("person", "subscribed", "Subscribed", "BOOLEAN", None),
    ("person", "bounced", "Bounced", "BOOLEAN", None),
    ("person", "outreachSelected", "Outreach selected", "BOOLEAN", None),
    ("person", "lastEmailedAt", "Last emailed at", "DATE_TIME", None),
    ("person", "contactSource", "Contact source", "SELECT",
     _options(["No Contact Source", "Website", "Manual Email", "BetterComms Email", "Other"])),
    ("person", "namedEmail", "Named email", "BOOLEAN", None),
    ("person", "emailsReceived", "Emails received", "NUMBER", None),
    ("person", "country", "Country", "TEXT", None),
    ("person", "lastCampaign", "Last campaign", "TEXT", None),
    # Multi-club officer: set when a Contact holds an Officer-role in more than one
    # club (the native single Company can't show that; the flag/count surface it).
    ("person", "multiClub", "In multiple clubs", "BOOLEAN", None),
    ("person", "clubCount", "Club count", "NUMBER", None),
    # Denormalised lifecycle stage of the club the Contact belongs to, so it's
    # visible/filterable on the Contact (Twenty can't show a nested relation field).
    ("person", "clubLifecycleStage", "Club lifecycle stage", "SELECT",
     _options(["Target", "Prospect", "Engaged", "Trial", "Customer", "Churned", "Suppressed"])),
    # ---- Opportunity ----
    ("opportunity", "bcOpportunityKey", "BC Opportunity key", "TEXT", None),
    ("opportunity", "modulesInScope", "Modules in scope", "MULTI_SELECT", MODULE_OPTS),
    ("opportunity", "oppSource", "Source", "SELECT",
     _options(["Inbound form", "Outbound campaign", "Referral", "Directory"])),
    ("opportunity", "lostReason", "Lost reason", "SELECT",
     _options(["Not interested", "No budget", "Competitor", "No response", "Other"])),
    # ---- Association ----
    ("association", "bcAssociationId", "BC Association Id", "TEXT", None),
    ("association", "shortCode", "Short code", "TEXT", None),
    ("association", "assocState", "State", "TEXT", None),
    ("association", "assocCountry", "Country", "TEXT", None),
    ("association", "clubCount", "Club count", "NUMBER", None),
    # ---- Membership (clubAssociation junction) ----
    ("clubAssociation", "isPrimary", "Is primary", "BOOLEAN", None),
    # ---- Officer role (personClub junction) ----
    ("personClub", "bcContactId", "BC Contact Id", "TEXT", None),
    ("personClub", "clubRole", "Club role", "SELECT",
     _options(["President", "Vice President", "Secretary", "Treasurer", "Registrar",
               "Coordinator", "Club contact", "Sponsor", "Other"])),
    ("personClub", "roleTitle", "Role title", "TEXT", None),
    ("personClub", "roleRank", "Role rank", "NUMBER", None),
    ("personClub", "outreachSelected", "Outreach selected", "BOOLEAN", None),
    # Per-club email + phone, so a club-specific contact detail is preserved on the
    # membership (and the "Officer roles" view shows role, email and mobile together)
    # even when it differs from the shared Contact's single canonical one.
    ("personClub", "email", "Email", "EMAILS", None),
    ("personClub", "phone", "Mobile", "PHONES", None),
    # ---- Touchpoint ----
    ("touchpoint", "touchpointType", "Type", "SELECT",
     _options(["Email sent", "Email delivered", "Email opened", "Email clicked",
               "Email bounced", "Email complaint", "Email unsubscribe", "Email reply",
               "Exported to comms", "Call", "Meeting", "Demo", "Trial start",
               "Trial end", "Onboarding enquiry", "Web milestone", "Note", "System"])),
    ("touchpoint", "direction", "Direction", "SELECT",
     _options(["Inbound", "Outbound", "System"])),
    ("touchpoint", "occurredAt", "Occurred at", "DATE_TIME", None),
    ("touchpoint", "subject", "Subject", "TEXT", None),
    ("touchpoint", "summary", "Summary", "TEXT", None),
    ("touchpoint", "channel", "Channel", "SELECT",
     _options(["Email", "Phone", "Web", "In person", "System"])),
    ("touchpoint", "externalRef", "External ref", "TEXT", None),
    ("touchpoint", "campaignName", "Campaign name", "TEXT", None),
    # ---- Email (bcEmail) ----
    ("bcEmail", "bcCampaignId", "BC Campaign Id", "TEXT", None),
    ("bcEmail", "sentAt", "Sent at", "DATE_TIME", None),
    ("bcEmail", "listName", "List name", "TEXT", None),
    ("bcEmail", "recipients", "Recipients", "NUMBER", None),
    ("bcEmail", "delivered", "Delivered", "NUMBER", None),
    ("bcEmail", "bounced", "Bounced", "NUMBER", None),
    ("bcEmail", "complaints", "Complaints", "NUMBER", None),
]

# Friendlier display labels for the two standard objects. The API names stay
# company / person (and the REST endpoints companies / people), so only what the UI
# shows changes. (nameSingular, labelSingular, labelPlural)
RELABEL = [
    ("company", "Club", "Clubs"),
    ("person", "Contact", "Contacts"),
]

# Opportunity pipeline stages (rewrite the built-in 'stage' SELECT options).
PIPELINE = ["Target", "Contacted", "Engaged", "Trial", "Proposal", "Won", "Lost / Dormant"]

# Relations created in a second pass: (from_object, field_name, label, to_object,
# relation_type, inverse_label). Twenty's relation payload is version-sensitive.
RELATIONS = [
    ("touchpoint", "company", "Club", "company", "MANY_TO_ONE", "Touchpoints"),
    ("touchpoint", "person", "Officer", "person", "MANY_TO_ONE", "Touchpoints"),
    ("touchpoint", "bcEmail", "Email", "bcEmail", "MANY_TO_ONE", "Touchpoints"),
    ("bcEmail", "company", "Club", "company", "MANY_TO_ONE", "Emails"),
    # Many-to-many between clubs and associations via the clubAssociation junction:
    # each membership links one club and one association. The inverse lists give the
    # two views — a company's "Memberships" and an association's "Member clubs".
    ("clubAssociation", "company", "Club", "company", "MANY_TO_ONE", "Memberships"),
    ("clubAssociation", "association", "Association", "association", "MANY_TO_ONE", "Member clubs"),
    # Many-to-many between people and clubs via the personClub junction: one row per
    # officer-at-a-club. Inverse lists give a club's "Officer roles" and a person's
    # "Club roles", so a shared officer is reachable from every club they serve.
    ("personClub", "person", "Officer", "person", "MANY_TO_ONE", "Club roles"),
    ("personClub", "company", "Club", "company", "MANY_TO_ONE", "Officer roles"),
]


def main():
    if not KEY:
        print("TWENTY_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    st, objs = _api("GET", "/rest/metadata/objects")
    if st != 200:
        print(f"could not list objects: {st} {objs}", file=sys.stderr)
        sys.exit(1)
    by_name = {o["nameSingular"]: o for o in objs["data"]}

    # 1. objects
    for spec in OBJECTS:
        n = spec["nameSingular"]
        if n in by_name:
            print(f"object  skip    {n}")
            continue
        s, r = _api("POST", "/rest/metadata/objects", spec)
        print(f"object  {'ok' if s in (200, 201) else 'ERR ' + str(s):<7} {n} {('' if s in (200,201) else json.dumps(r)[:200])}")

    # refresh after creating objects
    st, objs = _api("GET", "/rest/metadata/objects")
    by_name = {o["nameSingular"]: o for o in objs["data"]}
    field_names = {n: {f["name"] for f in o.get("fields", [])} for n, o in by_name.items()}

    # 1b. friendlier display labels on the standard objects (Company -> Clubs,
    # Person -> Contacts). Only the labels are sent: a standard object rejects edits
    # to isLabelSyncedWithName, and just diverging the label from the name is enough
    # (this is what Twenty's own rename UI does).
    for nameSingular, ls, lp in RELABEL:
        o = by_name.get(nameSingular)
        if not o:
            continue
        if o.get("labelSingular") == ls and o.get("labelPlural") == lp:
            print(f"label   skip    {nameSingular} ({ls}/{lp})")
            continue
        s, r = _api("PATCH", f"/rest/metadata/objects/{o['id']}",
                    {"labelSingular": ls, "labelPlural": lp})
        print(f"label   {'ok' if s in (200, 201) else 'ERR ' + str(s):<7} "
              f"{nameSingular} -> {ls}/{lp} {('' if s in (200, 201) else json.dumps(r)[:200])}")

    # 2. fields
    created = skipped = errored = 0
    for obj, name, label, ftype, options in FIELDS:
        o = by_name.get(obj)
        if not o:
            print(f"field   ERR     {obj}.{name} (object missing)")
            errored += 1
            continue
        if name in field_names.get(obj, set()):
            skipped += 1
            continue
        body = {"name": name, "label": label, "type": ftype,
                "objectMetadataId": o["id"], "isLabelSyncedWithName": False}
        if options is not None:
            body["options"] = options
        s, r = _api("POST", "/rest/metadata/fields", body)
        if s in (200, 201):
            created += 1
        else:
            errored += 1
            print(f"field   ERR {s} {obj}.{name} ({ftype}) {json.dumps(r)[:200]}")
    print(f"fields: created={created} skipped={skipped} errored={errored}")

    # 3. pipeline stages on opportunity.stage
    opp = by_name.get("opportunity")
    stage = next((f for f in opp.get("fields", []) if f["name"] == "stage"), None) if opp else None
    if stage:
        cur = [o.get("value") for o in (stage.get("options") or [])]
        want = [_value(s) for s in PIPELINE]
        if cur != want:
            s, r = _api("PATCH", f"/rest/metadata/fields/{stage['id']}",
                        {"options": _options(PIPELINE),
                         "defaultValue": "'" + _value(PIPELINE[0]) + "'"})
            print(f"stage   {'ok' if s in (200,201) else 'ERR ' + str(s)} {('' if s in (200,201) else json.dumps(r)[:200])}")
        else:
            print("stage   skip (already set)")

    # 4. relations (best-effort; payload is version-sensitive)
    for from_obj, fname, label, to_obj, rtype, inv in RELATIONS:
        fo, to = by_name.get(from_obj), by_name.get(to_obj)
        if not fo or not to:
            continue
        if fname in field_names.get(from_obj, set()):
            print(f"relate  skip    {from_obj}.{fname}")
            continue
        body = {
            "name": fname, "label": label, "type": "RELATION",
            "objectMetadataId": fo["id"],
            "relationCreationPayload": {
                "targetObjectMetadataId": to["id"],
                "targetFieldLabel": inv,
                "targetFieldIcon": "IconLink",
                "type": rtype,
            },
        }
        s, r = _api("POST", "/rest/metadata/fields", body)
        print(f"relate  {'ok' if s in (200,201) else 'ERR ' + str(s):<7} {from_obj}.{fname} -> {to_obj} ({rtype}) {('' if s in (200,201) else json.dumps(r)[:240])}")


if __name__ == "__main__":
    main()
