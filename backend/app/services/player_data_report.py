"""A PDF of the personal information we hold about ONE person, for a data access request.

A Super Admin generates it (``routers/privacy_requests.py``), reads it, and sends it
to the person once they have checked who is asking. It is built for the person to
read, not for staff: plain words, no table names.

WHAT IT SHOWS
-------------
  * Every player record for the person at every club (the participant id is shared
    across clubs, ``player_privacy.siblings``): the personal fields themselves.
  * Their membership record, comms contact entries, sign-in account and other names.
  * Cricket records as counts, plus a list of the matches they are recorded in.
  * Fee and payment records as a COUNT only. Amounts and dates are not printed.
  * Whether their request to be removed has been acted on.

WHAT IT DOES NOT SHOW, ON PURPOSE
---------------------------------
  * Another person's details. A family link says a link exists; it never prints who.
    An emergency contact says it is held; it never prints the number.
  * Free-text notes. Their presence is stated and the person is told to ask for
    them, because a note can hold anything about anyone and a human should read it
    before it leaves.
  * Password hashes, tokens and internal ids other than the ones the person already
    sees (their participant id).

Every statement is generated from the database at the time. Where a source table is
missing on a deployment, that section is simply absent, never invented.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.services import player_privacy, privacy_evidence
from app.services.privacy_evidence import _latin1

CONTACT = "support@bettersports.com.au"

# Friendly names for the cricket-record tables. Anything not listed falls back to a
# readable version of the table name, so a table added later is still counted.
_RECORD_LABELS = {
    "batting_innings": "Batting innings",
    "bowling_spells": "Bowling spells",
    "fielding_stats": "Fielding records",
    "game_appearances": "Match appearances",
    "fall_of_wickets": "Fall of wicket entries",
    "partnerships": "Batting partnerships",
    "bowler_wickets": "Wickets taken",
    "fielder_wickets": "Catches and dismissals",
    "milestones": "Milestones",
    "player_season_stats": "Season statistics",
    "player_season_grade_stats": "Season statistics by grade",
    "manual_batting_innings": "Batting innings (entered by the club)",
    "manual_bowling_spells": "Bowling spells (entered by the club)",
    "manual_fielding_stats": "Fielding records (entered by the club)",
    "manual_season_adjustments": "Season adjustments (entered by the club)",
    "manual_career_adjustments": "Career adjustments (entered by the club)",
    "player_achievements": "Honours and achievements",
    "player_name_aliases": "Other names",
    "team_members": "Squad memberships",
}


_CRICKET_TABLES = frozenset(t for t in _RECORD_LABELS if t not in ("player_name_aliases", "team_members"))
_OWN_SECTION = frozenset({"fee_members", "family_members", "comms_contacts", "player_name_aliases"})
_MONEY_TABLE = re.compile(r"(payment|invoice|charge|merch_order|stripe|receipt|refund)", re.I)


def _label(table: str) -> str:
    return _RECORD_LABELS.get(table) or table.replace("_", " ").capitalize()


def _fmt_date(d) -> str:
    if d is None:
        return ""
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return d
    return f"{d.day} {d.strftime('%B %Y')}"


def _yes(v) -> str:
    return "Yes" if v else "No"


async def _rows(session, sql: str, params: dict) -> list:
    """Rows, or [] when the table is not on this database. A savepoint keeps a
    missing table from aborting the caller's transaction."""
    try:
        async with session.begin_nested():
            return list((await session.execute(text(sql), params)).mappings().all())
    except Exception:
        return []


async def _fk_counts(session, parent: str, ids: list[str]) -> dict[str, int]:
    """{table: rows} for every table with a single-column foreign key onto parent(id)."""
    if not ids:
        return {}
    fks = (await session.execute(text("""
        SELECT cl.relname, att.attname
          FROM pg_constraint c
          JOIN pg_class cl  ON cl.oid = c.conrelid
          JOIN pg_class ref ON ref.oid = c.confrelid
          JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = ANY(c.conkey)
         WHERE c.contype = 'f' AND ref.relname = :p AND array_length(c.conkey, 1) = 1
         ORDER BY cl.relname, att.attname
    """), {"p": parent})).fetchall()
    out: dict[str, int] = {}
    for tbl, col in fks:
        # Identifiers come from the catalogue, never from a caller.
        n = await session.scalar(text(f'SELECT COUNT(*) FROM "{tbl}" WHERE "{col}"::text = ANY(:ids)'), {"ids": ids})
        if n:
            out[tbl] = out.get(tbl, 0) + int(n)
    return out


# --------------------------------------------------------------------------- data

async def gather(session, player) -> dict:
    people = [player] + await player_privacy.siblings(session, player)
    ids = [str(p.id) for p in people]
    org_ids = sorted({str(p.organisation_id) for p in people if p.organisation_id})
    orgs = {str(r["id"]): r["name"] for r in await _rows(
        session, "SELECT id, name FROM organisations WHERE id::text = ANY(:o)", {"o": org_ids})}

    records = []
    for p in people:
        fields = [
            ("Name on record", p.name),
            ("Display name", getattr(p, "display_name_override", None)),
            ("Date of birth", _fmt_date(p.date_of_birth) if p.date_of_birth else None),
            ("Email address", p.email),
            ("Phone", p.phone),
            ("Gender", p.gender),
            ("Shirt number", p.shirt_number),
            ("Playing role", p.player_role),
            ("Batting hand", p.batting_hand),
            ("Bowling", " ".join(x for x in (p.bowling_action, p.bowling_type) if x) or None),
            ("Overseas player", p.overseas_country if p.is_overseas else None),
            ("Status at the club", p.status),
            ("Cricket Australia participant ID", p.grassroots_id),
            ("PlayHQ ID", p.playhq_id),
            ("CricketStatz ID", getattr(p, "cricketstatz_player_id", None)),
            ("Photograph held", _yes(p.photo_data or p.photo_url)),
            ("Action photograph held", _yes(p.hero_photo_data or p.hero_photo_url)),
            ("Has claimed this profile with a sign-in", _yes(p.claimed or p.user_id)),
        ]
        records.append({
            "club": orgs.get(str(p.organisation_id), "A club"),
            "fields": [(k, v) for k, v in fields if v not in (None, "")],
            "shown_publicly": p.is_public is not False,
            "hidden_at": p.privacy_hidden_at,
        })

    # Membership records. Free-text notes are never printed (see the module doc).
    members = await _rows(session, """
        SELECT organisation_id, full_name, email, mobile, current_tier, is_life_member, life_member_since,
               is_honorary, gender, shirt_size, pants_size, archived_at, created_at,
               (notes IS NOT NULL AND TRIM(notes) <> '') AS has_note
          FROM fee_members WHERE player_id::text = ANY(:p) ORDER BY created_at
    """, {"p": ids})
    member_ids = [str(r["id"]) for r in await _rows(
        session, "SELECT id FROM fee_members WHERE player_id::text = ANY(:p)", {"p": ids})]
    membership = [{
        "club": orgs.get(str(m["organisation_id"]), "A club"),
        "fields": [(k, v) for k, v in (
            ("Name", m["full_name"]), ("Email address", m["email"]), ("Mobile", m["mobile"]),
            ("Membership", m["current_tier"]),
            ("Life member", f"Yes, since {_fmt_date(m['life_member_since'])}" if m["is_life_member"] and m["life_member_since"]
             else ("Yes" if m["is_life_member"] else None)),
            ("Honorary member", "Yes" if m["is_honorary"] else None),
            ("Gender", m["gender"]), ("Shirt size", m["shirt_size"]), ("Pants size", m["pants_size"]),
            ("Record created", _fmt_date(m["created_at"])),
            ("Record archived", _fmt_date(m["archived_at"]) if m["archived_at"] else None),
            ("A free-text note is held", "Yes. Ask us and we will send it to you." if m["has_note"] else None),
        ) if v not in (None, "")],
    } for m in members]

    # Family links: that a link exists, never who is on the other end.
    fam = await _rows(session, """
        SELECT relationship, is_guardian FROM family_members
         WHERE player_id::text = ANY(:p) OR fee_member_id::text = ANY(:m)
    """, {"p": ids, "m": member_ids})

    fee_children = await _fk_counts(session, "fee_members", member_ids)
    # Fee, payment, invoice and shop-order tables: counted together, never itemised.
    # Everything else hanging off the membership (committee terms, volunteer hours,
    # qualifications, meetings) is listed by name with its count.
    money_rows = sum(n for t, n in fee_children.items() if _MONEY_TABLE.search(t))
    member_extras = {t: n for t, n in fee_children.items()
                     if not _MONEY_TABLE.search(t) and t not in ("family_members", "comms_contacts")}

    aliases = [r["alias_name"] for r in await _rows(
        session, "SELECT DISTINCT alias_name FROM player_name_aliases WHERE player_id::text = ANY(:p) ORDER BY alias_name",
        {"p": ids})]

    from app.services import privacy_email
    addrs = sorted(await privacy_email.addresses_for_players(session, ids))
    contacts = await _rows(session, """
        SELECT organisation_id, email, source, subscribed, unsubscribed_at, bounced, excluded
          FROM comms_contacts
         WHERE player_id::text = ANY(:p) OR member_id::text = ANY(:m) OR LOWER(email) = ANY(:a)
         ORDER BY email
    """, {"p": ids, "m": member_ids, "a": addrs})
    blocked = bool(addrs) and all([await privacy_email.is_removed_address(a, session) for a in addrs])

    user_ids = [str(p.user_id) for p in people if getattr(p, "user_id", None)]
    accounts = await _rows(session, "SELECT username, email, last_login_at FROM users WHERE id::text = ANY(:u)",
                           {"u": user_ids}) if user_ids else []

    linked = await _fk_counts(session, "players", ids)
    scouting = await _rows(session, """
        SELECT club_name, grade_name, (photo_data IS NOT NULL OR photo_url IS NOT NULL) AS has_photo
          FROM scouted_players
         WHERE internal_player_id::text = ANY(:p)
            OR (CAST(:g AS TEXT) IS NOT NULL AND grassroots_participant_id = CAST(:g AS TEXT))
    """, {"p": ids, "g": player.grassroots_id})

    ev = await privacy_evidence.gather(session, player)
    matches = [{"date": m["date"], "grade": m["grade"], "home": m["home"], "away": m["away"]} for m in ev["matches"]]

    audit = await player_privacy.contact_audit(session, player)

    return {
        "name": player.name,
        "primary_id": str(player.grassroots_id or player.id),
        "generated_on": datetime.now(timezone.utc).date(),
        "records": records,
        "membership": membership,
        "family_links": len(fam),
        "money_rows": money_rows,
        "aliases": aliases,
        "email_addresses": addrs,
        "email_blocked": blocked,
        "contacts": [{
            "club": orgs.get(str(c["organisation_id"]), "A club"), "email": c["email"], "source": c["source"],
            "subscribed": bool(c["subscribed"]), "unsubscribed_at": c["unsubscribed_at"],
            "bounced": bool(c["bounced"]), "excluded": bool(c["excluded"]),
        } for c in contacts],
        "accounts": [dict(a) for a in accounts],
        # Only scoring records are "cricket records". Anything else that points at the
        # player is listed under club involvement by a readable name, so a table added
        # later is still counted. What has its own section (the membership record, the
        # email list, family links, other names) is not repeated.
        "cricket_records": sorted(
            ((_label(t), n) for t, n in linked.items() if t in _CRICKET_TABLES), key=lambda x: x[0]),
        "admin_records": sorted(
            [(_label(t), n) for t, n in linked.items() if t not in _CRICKET_TABLES and t not in _OWN_SECTION]
            + [(_label(t), n) for t, n in member_extras.items()], key=lambda x: x[0]),
        "scouting": [dict(s) for s in scouting],
        "matches": matches,
        "contact_summary": audit.get("summary", {}),
        "hidden_at": player.privacy_hidden_at,
        "has_photo": any(bool(p.photo_data or p.photo_url or p.hero_photo_data or p.hero_photo_url) for p in people),
        "removed_at_request": player_privacy.is_privacy_hidden(player) and not player_privacy.is_name_match_hold(player),
    }


# ---------------------------------------------------------------------------- PDF

_GREEN = (0, 112, 74)
_INK = (24, 24, 24)
_MUTED = (96, 96, 96)
_SHADE = (244, 246, 245)


def render_pdf(data: dict) -> bytes:
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    name = data["name"]
    on = _fmt_date(data["generated_on"])

    class Doc(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 8.5)
            self.set_text_color(*_GREEN)
            self.cell(0, 5, "BetterCricket  |  BetterSports", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*_GREEN)
            self.set_line_width(0.5)
            self.line(self.l_margin, self.get_y() + 0.5, self.w - self.r_margin, self.get_y() + 0.5)
            self.ln(4)

        def footer(self):
            self.set_y(-13)
            self.set_font("Helvetica", "", 7.5)
            self.set_text_color(*_MUTED)
            self.cell(0, 4, _latin1(f"Personal information held about {name}  |  prepared {on}  |  confidential, for the named person only"),
                      align="L")
            self.set_x(self.w - self.r_margin - 25)
            self.cell(25, 4, f"Page {self.page_no()} of {{nb}}", align="R")

    pdf = Doc(format="A4", unit="mm")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 16, 18)
    pdf.set_title(_latin1(f"Personal information held about {name}"))
    pdf.set_author("BetterSports")
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    def para(t, size=10, bold=False, gap=2.2, color=_INK, italic=False):
        pdf.set_font("Helvetica", ("B" if bold else "") + ("I" if italic else ""), size)
        pdf.set_text_color(*color)
        pdf.multi_cell(W, 5.2, _latin1(t), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    def heading(t):
        if pdf.get_y() > pdf.h - 50:
            pdf.add_page()
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*_GREEN)
        pdf.cell(0, 7, _latin1(t), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def sub(t, keep=40):
        # `keep` is the room (mm) the table under it needs; a record that will not
        # fit starts on a fresh page rather than splitting across two.
        if pdf.get_y() > pdf.h - keep:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*_INK)
        pdf.cell(0, 6, _latin1(t), new_x="LMARGIN", new_y="NEXT")

    def kv(rows, key_w=62):
        rows = [(k, v) for k, v in rows if v not in (None, "")]
        if not rows:
            return
        with pdf.table(col_widths=(key_w, W - key_w), text_align=("LEFT", "LEFT"), line_height=5.2,
                       borders_layout="HORIZONTAL_LINES", first_row_as_headings=False,
                       padding=1.4, markdown=False) as table:
            for k, v in rows:
                row = table.row()
                row.cell(_latin1(str(k)), style=FontFace(emphasis="BOLD", color=_MUTED, size_pt=9))
                row.cell(_latin1(str(v)), style=FontFace(color=_INK, size_pt=9.5))
        pdf.ln(3)

    # ---- title block
    pdf.set_font("Helvetica", "B", 19)
    pdf.set_text_color(*_INK)
    pdf.multi_cell(W, 8.5, _latin1(f"Personal information we hold about {name}"), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    para(f"Prepared on {on} by BetterSports for the person named. Reference: player {data['primary_id']}.",
         size=9, color=_MUTED, gap=4)

    heading("About this document")
    para("This lists the personal information BetterCricket holds about you, as it stood on the date above. "
         "It covers BetterCricket's own records only. Your clubs keep records of their own (for example membership "
         "forms, spreadsheets and bank records), and Cricket Australia, PlayHQ and Play-Cricket keep theirs. We cannot "
         "see those, so they are not in this document. Please ask the club or organisation concerned if you want them.")
    para("We hold this information so that clubs can run their stats pages and club tools on BetterCricket. "
         "Nothing here is shown to anyone but you and the people at your club who look after the club's records, "
         "apart from what appears on a club's public match pages, which is described below.")

    # ---- at a glance
    heading("At a glance")
    cs = data["contact_summary"]
    held = lambda b: "Held" if b else "Not held"
    n_rec = len(data["records"])
    clubs = ", ".join(sorted({r["club"] for r in data["records"]}))
    ms = data["matches"]
    dated = [m["date"] for m in ms if m["date"]]
    status = ("Removed from the public website at your request"
              + (f" on {_fmt_date(data['hidden_at'])}" if data["hidden_at"] else "")
              if data["removed_at_request"] else
              ("Shown on the public website" if all(r["shown_publicly"] for r in data["records"]) else "Hidden from the public website"))
    kv([
        ("Player records", f"{n_rec} ({clubs})"),
        ("Public website", status),
        ("Photographs", "Held" if data["has_photo"] else "None held"),
        ("Date of birth", held(cs.get("date_of_birth"))),
        ("Email address", held(cs.get("email"))),
        ("Phone number", held(cs.get("phone"))),
        ("Postal address", held(cs.get("address"))),
        ("Emergency contact", held(cs.get("emergency_contact"))),
        ("Matches recorded", (f"{len(ms)} ({_fmt_date(min(dated))} to {_fmt_date(max(dated))})" if dated else str(len(ms)))),
        ("Membership records", str(len(data["membership"])) if data["membership"] else "None"),
        ("Fee and payment records", f"{data['money_rows']} (amounts and dates are not shown here)" if data["money_rows"] else "None"),
        ("Sign-in account", "Yes" if data["accounts"] else "None"),
        ("Club email list entries", str(len(data["contacts"])) if data["contacts"] else "None"),
    ])

    # ---- player records
    heading("Your player records")
    para("A player record is created for you at each club that records your matches. The same Cricket Australia "
         "participant ID links them.", size=9.5, color=_MUTED)
    for i, r in enumerate(data["records"], 1):
        sub(f"{r['club']}" + (f"  (record {i} of {n_rec})" if n_rec > 1 else ""),
            keep=min(30 + 6.4 * (len(r["fields"]) + 1), 150))
        kv(r["fields"] + [("Shown on the public website", _yes(r["shown_publicly"]))])

    if data["aliases"]:
        heading("Other names on record")
        para("Names we have linked to your records so that scorecards using a different spelling reach the right "
             "player: " + "; ".join(data["aliases"]) + ".")

    # ---- membership and communications
    if data["membership"] or data["family_links"] or data["contacts"] or data["accounts"] or data["money_rows"]:
        heading("Membership, family and communications records")
    for m in data["membership"]:
        sub(f"Membership record: {m['club']}", keep=min(30 + 6.4 * len(m["fields"]), 150))
        kv(m["fields"])
    if data["family_links"]:
        para(f"Your records are linked to {data['family_links']} family record(s). We do not print other people's details here.")
    if data["money_rows"]:
        para(f"There are {data['money_rows']} fee and payment record(s) against your membership. Amounts and dates are not "
             f"printed in this document. Ask us and we will send them to you separately.")
    if data["contacts"]:
        sub("Club email list")
        kv([(c["email"], ", ".join(x for x in (
            c["club"], "subscribed" if c["subscribed"] else "not subscribed",
            "unsubscribed " + _fmt_date(c["unsubscribed_at"]) if c["unsubscribed_at"] else "",
            "address bounced" if c["bounced"] else "", "excluded from emails" if c["excluded"] else "") if x))
            for c in data["contacts"]], key_w=70)
    if data["email_addresses"]:
        para("We will not send email to " + ("any of the addresses we hold for you." if data["email_blocked"]
             else "the addresses we hold for you once you ask us to stop."), gap=3)
    for a in data["accounts"]:
        sub("Sign-in account")
        kv([("Username", a.get("username")), ("Email address", a.get("email")),
            ("Last signed in", _fmt_date(a.get("last_login_at")) if a.get("last_login_at") else None)])

    # ---- cricket records
    heading("Cricket records")
    para("These are the scoring records that make up your statistics. We show how many of each we hold.", size=9.5, color=_MUTED)
    if data["cricket_records"]:
        kv([(label, str(n)) for label, n in data["cricket_records"]], key_w=90)
    else:
        para("No scoring records are held against your player records.")
    if data["admin_records"]:
        sub("Club involvement and other records")
        kv([(label, str(n)) for label, n in data["admin_records"]], key_w=90)
    for s in data["scouting"]:
        para("A scouting record exists for you in BetterIQ's opposition notes" + (f" ({s['club_name']})" if s.get("club_name") else "")
             + (", with a photograph." if s.get("has_photo") else "."))
    if data["removed_at_request"]:
        para("Because you asked to be removed, your name shows as ******** on public match pages, and your profile "
             "page shows \"Player not found\". The match results themselves stay, because other players' scores and "
             "the team totals depend on them.", gap=3)
    else:
        para("Your name and match statistics appear on your club's public match pages, ladders, records and awards.", gap=3)

    # ---- not covered + contact
    heading("What this document does not cover")
    for t in ("Records your clubs keep outside BetterCricket, and records held by Cricket Australia, PlayHQ or Play-Cricket.",
              "Copies of this website that other sites, search engines or people have made.",
              "Free-text notes, and the amounts and dates of fee records. These are available on request."):
        para("- " + t, gap=1)
    para("")
    para(f"If anything here is wrong, or you would like it corrected or removed, reply to the person who sent you this, "
         f"or email {CONTACT}.")

    # ---- appendix: matches
    if ms:
        pdf.add_page()
        heading("Appendix: matches you are recorded in")
        para(f"{len(ms)} match(es), oldest first.", size=9.5, color=_MUTED)
        rows = []
        for m in ms:
            teams = f"{m['home']} v {m['away']}" if m.get("home") and m.get("away") else "Match"
            rows.append((_fmt_date(m["date"]) or "Date not recorded", f"{m['grade'] or 'Grade not recorded'}: {teams}"))
        kv(rows, key_w=38)
    return bytes(pdf.output())


def filename_for(name: str, on: Optional[date] = None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "player").lower()).strip("-") or "player"
    return f"data-held-{slug}-{(on or datetime.now(timezone.utc).date()).isoformat()}.pdf"
