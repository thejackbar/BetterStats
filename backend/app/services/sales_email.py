"""Sales Workspace — templated + custom emails sent one-to-one from the
Workspace drawer. This is the lightweight single-recipient pattern
``services/user_invite.py`` already uses (build an EmailMessage, send it
through the configured provider), NOT a second implementation of the full
BetterComms campaign/audience system — a sales rep emailing one contact has
nothing to do with an audience/segment.

Every outbound link gets UTM tags via ``routers/comms.py``'s own
``_apply_utm`` — ``utm_source='sales'``, ``utm_medium='email'``,
``utm_campaign=<template key>``, ``utm_content=<sending rep's username>``,
and ``utm_id=<club's own utm_code>`` (auto-generated + persisted the same
way ``services/club_directory.py`` already does for a crawled club, if this
one doesn't have one yet) — so a later site visit or trial signup from this
link can be tied back to both the club AND which rep sent it, per direct
instruction.
"""
from __future__ import annotations

from typing import Optional

from app.config.settings import settings
from app.services import email_service

TEMPLATE_LABELS = {
    "information": "Send information",
    "voicemail_followup": "Email following voicemail",
    "trial_information": "Trial information",
    "trial_extension": "Wants a trial extension",
    "demo": "Book a demo",
    "subscribe": "Wants to buy/subscribe",
    "custom": "Custom email",
}
# The comms_templates row a key's content is seeded/read from — same as
# TEMPLATE_LABELS (the rep-facing dropdown text) for every key EXCEPT
# 'custom'/'subscribe'/'trial_extension': the dropdown reads the outcome the
# rep is acting on ("Custom email", "Wants to buy/subscribe", "Wants a trial
# extension"), but the editable templates behind them carry more descriptive
# names in Comms -> Templates for the super admin maintaining them there.
# Falls back to TEMPLATE_LABELS for any key with no override.
TEMPLATE_DB_NAMES = {
    "custom": "Custom sales rep email",
    "subscribe": "Sales rep subscribe link",
    "trial_extension": "Sales rep trial extension",
}


def _db_name(key: str) -> Optional[str]:
    return TEMPLATE_DB_NAMES.get(key, TEMPLATE_LABELS.get(key))


# Every key has a body built/loaded here — 'custom' used to mean "subject/
# body typed by the rep from a blank form", but now opens the same way as
# the rest: pre-filled from its own editable template, which the rep edits
# in Design mode rather than starting from nothing.
BUILT_IN_TEMPLATES = (
    "information", "voicemail_followup", "trial_information", "trial_extension", "demo", "subscribe", "custom",
)


def _greeting(name: Optional[str]) -> str:
    parts = (name or "").strip().split()
    first = parts[0] if parts else ""
    return f"Hi {first}," if first else "Hi there,"


def _wrap(title: str, body_html: str) -> str:
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:14px;color:#555">BetterCricket</p>
      <h1 style="font-size:20px;margin:0 0 16px">{title}</h1>
      {body_html}
    </div>
    """


def _button(label: str, url: str) -> str:
    return (
        f'<p style="margin:24px 0"><a href="{url}" style="display:inline-block;'
        "background:#16C784;color:#fff;text-decoration:none;padding:12px 24px;"
        f'border-radius:6px;font-weight:bold;font-size:14px">{label}</a></p>'
    )


def _render_template_hardcoded(
    key: str, *, contact_name: Optional[str], club_name: str, rep_name: str,
    calendly_url: Optional[str] = None,
) -> tuple[str, str, str]:
    """The original hardcoded Python builder for a BUILT_IN_TEMPLATES key —
    kept as the fallback ``render_template`` (below) uses when the outreach
    org isn't configured yet, or its seeded CommsTemplate row is missing
    (e.g. a fresh/local environment with no marketing org set up). Raises
    ValueError for an unknown key."""
    if key not in BUILT_IN_TEMPLATES:
        raise ValueError(f"'{key}' is not a built-in template")

    greeting = _greeting(contact_name)
    base = settings.public_base_url

    if key == "information":
        subject = f"BetterCricket for {club_name}"
        body = (
            f'<p style="font-size:14px;line-height:1.5">{greeting} thanks for your interest in '
            f"BetterCricket — stats, team selection, availability, social posts and more, "
            f"all in one place for {club_name}.</p>"
            f'<p style="font-size:14px;line-height:1.5">Have a look through what’s on offer:</p>'
            + _button("See BetterCricket", base)
            + '<p style="font-size:14px;line-height:1.5">Happy to answer any questions — just reply to this email.</p>'
        )
        text = (
            f"{greeting} thanks for your interest in BetterCricket for {club_name}. "
            f"Have a look through what's on offer: {base} "
            "Happy to answer any questions — just reply to this email."
        )
    elif key == "voicemail_followup":
        subject = f"BetterCricket for {club_name} — following up"
        body = (
            f'<p style="font-size:14px;line-height:1.5">{greeting} I tried calling you just now '
            f"but couldn't get through, so I've left a voicemail. Wanted to follow up here too — "
            f"BetterCricket is stats, team selection, availability, social posts and more, "
            f"all in one place for {club_name}.</p>"
            f'<p style="font-size:14px;line-height:1.5">Have a look through what’s on offer:</p>'
            + _button("See BetterCricket", base)
            + '<p style="font-size:14px;line-height:1.5">Happy to answer any questions — just reply to this email, or give me a call back.</p>'
        )
        text = (
            f"{greeting} I tried calling you just now but couldn't get through, so I've left a "
            f"voicemail. Wanted to follow up here too — BetterCricket for {club_name}. "
            f"Have a look through what's on offer: {base} "
            "Happy to answer any questions — just reply to this email, or give me a call back."
        )
    elif key == "trial_information":
        subject = f"Start your free BetterCricket trial — {club_name}"
        steps = (
            '<ol style="font-size:14px;line-height:1.8;padding-left:20px">'
            "<li>Go to BetterCricket</li><li>Search for your club</li>"
            "<li>Select your club</li><li>Create your admin account</li>"
            "<li>Choose the modules you want</li><li>Start your 14-day trial — no card required</li>"
            "</ol>"
        )
        body = (
            f'<p style="font-size:14px;line-height:1.5">{greeting} here’s how to get {club_name} '
            f"started on a free trial:</p>{steps}"
            + _button("Start your trial", f"{base}/trial")
        )
        text = (
            f"{greeting} here's how to get {club_name} started on a free trial: "
            "1) Go to BetterCricket 2) Search for your club 3) Select your club "
            "4) Create your admin account 5) Choose the modules you want "
            f"6) Start your 14-day trial — no card required. {base}/trial"
        )
    elif key == "trial_extension":
        subject = f"Your BetterCricket trial extension for {club_name}"
        body = (
            f'<p style="font-size:14px;line-height:1.5">{greeting} no problem — I\'ve extended '
            f"{club_name}'s BetterCricket trial so you've got more time to get everything set up.</p>"
            + _button("Log in to BetterCricket", f"{base}/login")
            + '<p style="font-size:14px;line-height:1.5">Let me know if there\'s anything I can help with in the meantime.</p>'
        )
        text = (
            f"{greeting} no problem — I've extended {club_name}'s BetterCricket trial so you've "
            f"got more time to get everything set up. {base}/login "
            "Let me know if there's anything I can help with in the meantime."
        )
    elif key == "demo":
        subject = f"Book a demo — BetterCricket for {club_name}"
        if calendly_url:
            body = (
                f'<p style="font-size:14px;line-height:1.5">{greeting} happy to walk you through '
                f"BetterCricket for {club_name} — pick a time that suits:</p>"
                + _button("Book a time", calendly_url)
            )
            text = f"{greeting} happy to walk you through BetterCricket for {club_name}. Book a time: {calendly_url}"
        else:
            body = (
                f'<p style="font-size:14px;line-height:1.5">{greeting} happy to walk you through '
                f"BetterCricket for {club_name} — reply to this email with a couple of times that "
                "suit and I'll lock one in.</p>"
            )
            text = (
                f"{greeting} happy to walk you through BetterCricket for {club_name} — reply to "
                "this email with a couple of times that suit and I'll lock one in."
            )
    elif key == "subscribe":
        subject = f"Get {club_name} set up on BetterCricket"
        body = (
            f'<p style="font-size:14px;line-height:1.5">{greeting} great news — let\'s get '
            f"{club_name} set up on a paid BetterCricket subscription.</p>"
            '<p style="font-size:14px;line-height:1.5">Log in to your account and head to Account '
            "to choose your modules and subscribe:</p>"
            + _button("Log in to subscribe", f"{base}/login")
            + '<p style="font-size:14px;line-height:1.5">Happy to answer any questions — just reply to this email.</p>'
        )
        text = (
            f"{greeting} great news — let's get {club_name} set up on a paid BetterCricket "
            f"subscription. Log in to your account and head to Account to choose your modules and "
            f"subscribe: {base}/login "
            "Happy to answer any questions — just reply to this email."
        )
    else:  # custom — no fixed pitch, just a blank canvas to write into
        subject = f"BetterCricket — {club_name}"
        body = f'<p style="font-size:14px;line-height:1.5">{greeting}</p><p style="font-size:14px;line-height:1.5"></p>'
        text = f"{greeting}\n\n"

    signoff_html = f'<p style="font-size:13px;color:#555;margin-top:24px">{rep_name}</p>'
    return subject, _wrap(subject, body + signoff_html), f"{text}\n\n{rep_name}"


# ─── Editable templates (BetterAdmin -> Comms -> Templates) ──────────────────
# The three built-in emails are seeded as ordinary comms_templates rows in the
# platform's marketing outreach org (services/marketing_org.get_outreach_org)
# rather than staying hardcoded Python — a super admin edits them from the
# normal Templates screen, with the normal HTML/Design/Preview editor, same as
# every other email template in the app. {{first_name}}/{{club}} reuse the
# SAME merge-variable names BetterComms campaigns already use
# (routers/comms.py's MERGE_VARIABLES); {{rep_name}} and {{booking_block}} are
# two sales-specific tokens (not in that list — they're irrelevant to a club's
# own campaign editor) substituted the same way via routers/comms.py's _merge.
_SEED_BODY = {
    "information": (
        "<p>Hi {{first_name}},</p>"
        "<p>Thanks for your interest in BetterCricket — stats, team selection, availability, "
        "social posts and more, all in one place for {{club}}.</p>"
        "<p>Have a look through what's on offer:</p>"
        '<p><a href="{base}" style="display:inline-block;background:#16C784;color:#fff;'
        'text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;'
        'font-size:14px">See BetterCricket</a></p>'
        "<p>Happy to answer any questions — just reply to this email.</p>"
        "<p>Regards,<br>{{rep_name}}<br>BetterCricket</p>"
    ),
    # Seeded from information's own layout (intro line, then a button) per
    # direct instruction, reworded for a rep following up in writing right
    # after a call that went to voicemail.
    "voicemail_followup": (
        "<p>Hi {{first_name}},</p>"
        "<p>I tried calling you just now but couldn't get through, so I've left a voicemail. "
        "Wanted to follow up here too — BetterCricket is stats, team selection, availability, "
        "social posts and more, all in one place for {{club}}.</p>"
        "<p>Have a look through what's on offer:</p>"
        '<p><a href="{base}" style="display:inline-block;background:#16C784;color:#fff;'
        'text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;'
        'font-size:14px">See BetterCricket</a></p>'
        "<p>Happy to answer any questions — just reply to this email, or give me a call back.</p>"
        "<p>Regards,<br>{{rep_name}}<br>BetterCricket</p>"
    ),
    "trial_information": (
        "<p>Hi {{first_name}},</p>"
        "<p>Here's how to get {{club}} started on a free trial:</p>"
        '<ol style="padding-left:20px">'
        "<li>Go to BetterCricket</li><li>Search for your club</li>"
        "<li>Select your club</li><li>Create your admin account</li>"
        "<li>Choose the modules you want</li><li>Start your 14-day trial — no card required</li>"
        "</ol>"
        '<p><a href="{base}/trial" style="display:inline-block;background:#16C784;color:#fff;'
        'text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;'
        'font-size:14px">Start your trial</a></p>'
        "<p>Regards,<br>{{rep_name}}<br>BetterCricket</p>"
    ),
    # Seeded from trial_information's own layout (intro line, then a button)
    # per direct instruction, reworded for a club that's ready to move onto a
    # paid subscription rather than start a trial. Subscribing itself happens
    # from inside the app (Account -> Subscribe), so the button sends them to
    # log in rather than inventing a public "/subscribe" page that doesn't
    # exist.
    "trial_extension": (
        "<p>Hi {{first_name}},</p>"
        "<p>No problem — I've extended {{club}}'s BetterCricket trial so you've got more time "
        "to get everything set up.</p>"
        '<p><a href="{base}/login" style="display:inline-block;background:#16C784;color:#fff;'
        'text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;'
        'font-size:14px">Log in to BetterCricket</a></p>'
        "<p>Let me know if there's anything I can help with in the meantime.</p>"
        "<p>Regards,<br>{{rep_name}}<br>BetterCricket</p>"
    ),
    "demo": (
        "<p>Hi {{first_name}},</p>"
        "<p>Happy to walk you through BetterCricket for {{club}}.</p>"
        "{{booking_block}}"
        "<p>Regards,<br>{{rep_name}}<br>BetterCricket</p>"
    ),
    # Seeded from information's own layout (intro line, then a button) per
    # direct instruction, reworded for a club ready to subscribe now.
    "subscribe": (
        "<p>Hi {{first_name}},</p>"
        "<p>Great news — let's get {{club}} set up on a paid BetterCricket subscription.</p>"
        "<p>Log in to your account and head to Account to choose your modules and subscribe:</p>"
        '<p><a href="{base}/login" style="display:inline-block;background:#16C784;color:#fff;'
        'text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;'
        'font-size:14px">Log in to subscribe</a></p>'
        "<p>Happy to answer any questions — just reply to this email.</p>"
        "<p>Regards,<br>{{rep_name}}<br>BetterCricket</p>"
    ),
    # A full standalone document (dark theme, its own <head>/<body>), unlike
    # the three light-shell fragments above — render_template's _is_full_doc
    # check means this is used AS-IS, never re-wrapped in _wrap()'s own light
    # shell. {{utm_code}} is placed directly in each link's own query string
    # (not the automatic per-club utm_id apply_sales_utm adds afterwards) —
    # per the template as given; routers/comms.py's _apply_utm only adds a
    # key that ISN'T already on the link, so this hand-placed utm_source
    # survives untouched and utm_id is appended alongside it.
    "custom": '''<!DOCTYPE html>
<html lang="en-AU">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark light">
    <meta name="supported-color-schemes" content="dark light">
    <title>BetterCricket</title>
  </head>

  <body style="margin:0; padding:0; background-color:#0b1220;">

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0b1220;">
      <tbody>
        <tr>
          <td align="center" style="padding:28px 12px;">

            <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px; max-width:600px; background-color:#0b1220; border:1px solid #1d2331; border-radius:12px;">
              <tbody>

                <!-- BetterCricket Header -->
                <tr>
                  <td align="center" style="padding:30px 36px 0 36px;">
                    <a
                      href="{base}?utm_source={{utm_code}}&amp;utm_medium=sales_email&amp;utm_campaign=rep_{{rep_name}}&amp;utm_content=header_logo"
                      style="text-decoration:none;"
                    >
                      <img
                        src="{base}/email/bettercricket-logo.png"
                        width="64"
                        alt="BetterCricket"
                        style="display:block; border:0; margin:0 auto 8px auto;"
                      >

                      <span style="font-family:'Helvetica Neue', Helvetica, Arial, sans-serif; font-size:21px; line-height:26px; font-weight:bold; letter-spacing:-0.3px; color:#e6e8ef;">
                        Better<span style="color:#16C784;">Cricket</span>
                      </span>
                    </a>
                  </td>
                </tr>

                <!-- Email Body -->
                <tr>
                  <td style="padding:30px 36px 0 36px;">

                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tbody>

                        <!-- Greeting -->
                        <tr>
                          <td style="padding-bottom:18px; font-family:'Helvetica Neue', Helvetica, Arial, sans-serif; font-size:15px; line-height:24px; color:#e6e8ef;">
                            Hi {{first_name}},
                          </td>
                        </tr>

                        <!-- Message -->
                        <tr>
                          <td style="padding-bottom:28px; font-family:'Helvetica Neue', Helvetica, Arial, sans-serif; font-size:15px; line-height:24px; color:#e6e8ef;">
                            Enter your email message here
                          </td>
                        </tr>

                      </tbody>
                    </table>

                  </td>
                </tr>

                <!-- Sales Rep Signature -->
                <tr>
                  <td style="padding:0 36px 30px 36px;">
                    <span style="font-family:'Helvetica Neue', Helvetica, Arial, sans-serif; font-size:15px; line-height:24px; color:#e6e8ef;">
                      Regards,<br><br>

                      {{rep_name}}<br>

                      <a
                        href="{base}?utm_source={{utm_code}}&amp;utm_medium=sales_email&amp;utm_campaign=rep_{{rep_name}}&amp;utm_content=signature"
                        style="font-weight:bold; color:#16C784; text-decoration:none;"
                      >
                        BetterCricket
                      </a>
                    </span>
                  </td>
                </tr>

                <!-- Divider -->
                <tr>
                  <td style="padding:0 36px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tbody>
                        <tr>
                          <td style="border-top:1px solid #1d2331; height:1px; line-height:1px; font-size:1px;">
                            &nbsp;
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </td>
                </tr>

                <!-- Footer -->
                <tr>
                  <td align="center" style="padding:16px 36px 24px 36px;">
                    <span style="font-family:'Helvetica Neue', Helvetica, Arial, sans-serif; font-size:12px; line-height:18px; color:#8a90a2;">
                      The platform Australian cricket clubs run on<br>

                      <a
                        href="{base}?utm_source={{utm_code}}&amp;utm_medium=sales_email&amp;utm_campaign=rep_{{rep_name}}&amp;utm_content=footer"
                        style="color:#16C784; text-decoration:none;"
                      >
                        betterat.cricket
                      </a>
                    </span>
                  </td>
                </tr>

              </tbody>
            </table>

          </td>
        </tr>
      </tbody>
    </table>

  </body>
</html>''',
}
_SEED_SUBJECT = {
    "information": "BetterCricket for {{club}}",
    "voicemail_followup": "BetterCricket for {{club}} — following up",
    "trial_information": "Start your free BetterCricket trial — {{club}}",
    "trial_extension": "Your BetterCricket trial extension for {{club}}",
    "demo": "Book a demo — BetterCricket for {{club}}",
    "subscribe": "Get {{club}} set up on BetterCricket",
    "custom": "",
}


async def seed_sales_templates(session) -> int:
    """Insert every BUILT_IN_TEMPLATES row into the outreach org's
    comms_templates library, once — called on demand (email_templates GET) so
    it self-heals for an environment that only just configured its outreach
    org, same "call it cheaply and let it no-op" pattern comms.py's own
    seed_starter_templates uses. A same-named row a super admin has since
    edited is left alone (ON CONFLICT DO NOTHING) — unlike the general
    starter-template seed, there's no "empty skeleton" self-heal here, since
    none of these are ever auto-created empty. Returns the count inserted."""
    from app.services.marketing_org import get_outreach_org
    org = await get_outreach_org(session)
    if org is None:
        return 0
    from sqlalchemy import text as _text
    base = settings.public_base_url
    total = 0
    for key in BUILT_IN_TEMPLATES:
        result = await session.execute(
            _text("""
                INSERT INTO comms_templates (id, organisation_id, name, subject, html)
                VALUES (gen_random_uuid(), :org_id, :name, :subject, :html)
                ON CONFLICT (organisation_id, name) DO NOTHING
            """),
            {
                "org_id": org.id, "name": _db_name(key),
                "subject": _SEED_SUBJECT[key],
                # Plain substring replace, NOT str.format() — the body also
                # holds {{merge_token}} placeholders for _merge() to resolve
                # at render time, and .format() treats "{{"/"}}" as an escape
                # sequence for a literal brace, silently collapsing every
                # {{first_name}} down to a bare {first_name} before it's even
                # stored. Found by the verification script, not by reading
                # the code — the corruption is invisible until you look at
                # what actually landed in the row.
                "html": _SEED_BODY[key].replace("{base}", base),
            },
        )
        total += result.rowcount or 0
    return total


async def _load_template_row(session, key: str):
    from sqlalchemy import select as _select
    from app.services.marketing_org import get_outreach_org
    from app.models.db import CommsTemplate
    org = await get_outreach_org(session)
    if org is None:
        return None
    return await session.scalar(
        _select(CommsTemplate).where(
            CommsTemplate.organisation_id == org.id,
            CommsTemplate.name == _db_name(key),
        )
    )


def _booking_block(club_name: str, calendly_url: Optional[str]) -> str:
    if calendly_url:
        return (
            f'<p><a href="{calendly_url}" style="display:inline-block;background:#16C784;'
            'color:#fff;text-decoration:none;padding:12px 24px;border-radius:6px;'
            'font-weight:bold;font-size:14px">Book a time</a></p>'
        )
    return (
        f"<p>Reply to this email with a couple of times that suit {club_name} and I'll lock one in.</p>"
    )


async def render_template(
    session, key: str, *, contact_name: Optional[str], club_name: str, rep_name: str,
    calendly_url: Optional[str] = None, utm_code: str = "",
) -> tuple[str, str, str]:
    """Returns (subject, html, text) for a BUILT_IN_TEMPLATES key — from the
    editable outreach-org CommsTemplate row when one exists, else the
    original hardcoded builder (see _render_template_hardcoded's docstring
    for when that fallback applies). Raises ValueError for an unknown key,
    same as the hardcoded builder. utm_code feeds the {{utm_code}} merge
    token the 'custom' template hand-places into its own links — the other
    three templates don't reference it, so it's a harmless unused variable
    for them."""
    if key not in BUILT_IN_TEMPLATES:
        raise ValueError(f"'{key}' is not a built-in template")
    row = await _load_template_row(session, key)
    if row is None or not (row.html or "").strip():
        return _render_template_hardcoded(
            key, contact_name=contact_name, club_name=club_name, rep_name=rep_name,
            calendly_url=calendly_url,
        )
    from app.routers.comms import _merge, _is_full_doc, _html_to_text
    name_parts = (contact_name or "").strip().split()
    ctx = {
        # first_name/name/club keep the SAME meaning comms.py's own merge
        # variables have (bare values, not a pre-built greeting phrase) —
        # the seeded body spells out "Hi {{first_name}}," itself.
        "first_name": name_parts[0] if name_parts else "there",
        "name": (contact_name or "").strip() or "there",
        "club": club_name,
        "rep_name": rep_name,
        "booking_block": _booking_block(club_name, calendly_url),
        "utm_code": utm_code or "",
    }
    subject = _merge(row.subject or TEMPLATE_LABELS[key], ctx)
    merged_body = _merge(row.html or "", ctx)
    html = merged_body if _is_full_doc(merged_body) else _wrap(subject, merged_body)
    text = _html_to_text(html)
    return subject, html, text


async def render_template_preview(
    session, key: str, *, contact_name: Optional[str], club_name: str, rep_name: str,
    calendly_url: Optional[str] = None, utm_code: str = "",
) -> tuple[str, str]:
    """Same rendering as render_template, without sending — the Sales
    Workspace's Send Email form uses this to pre-fill the Design editor with
    real, already-merged content once a template is picked, which the rep
    then edits before Send actually fires."""
    subject, html, _text = await render_template(
        session, key, contact_name=contact_name, club_name=club_name,
        rep_name=rep_name, calendly_url=calendly_url, utm_code=utm_code,
    )
    return subject, html


def apply_sales_utm(html: str, *, template_key: str, rep_username: str, utm_code: Optional[str]) -> str:
    from app.routers.comms import _apply_utm
    return _apply_utm(
        html,
        {"utm_source": "sales", "utm_medium": "email", "utm_campaign": template_key, "utm_content": rep_username},
        utm_code=utm_code,
    )


async def send_sales_email(
    *, to_email: str, to_name: Optional[str], subject: str, html: str, text: str,
    rep_name: str, rep_email: Optional[str],
) -> None:
    """Sends immediately and RAISES on failure — unlike user_invite.py's
    best-effort emails (the account exists regardless of delivery), this is
    an explicit "send this now" action a rep is watching for a result on.
    from_email stays the platform's own verified sending address (spoofing
    an arbitrary from-address would fail SPF/DKIM); reply_to is the rep's
    own address so a reply reaches them directly."""
    msg = email_service.EmailMessage(
        to_email=to_email,
        to_name=to_name,
        subject=subject,
        html=html,
        text=text,
        from_email=settings.email_from_address,
        from_name=rep_name or settings.email_from_name,
        reply_to=rep_email or settings.email_reply_to,
        configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
    )
    result = await email_service.get_email_provider().send(msg)
    if not result.ok:
        raise RuntimeError(result.error or "Email provider did not confirm delivery")
