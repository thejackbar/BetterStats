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

import html as _html
from typing import Optional

from app.config.settings import settings
from app.services import email_service

TEMPLATE_LABELS = {
    "information": "Send information",
    "trial_information": "Trial information",
    "demo": "Book a demo",
    "custom": "Custom email",
}
# Every key except 'custom' has a body built here; 'custom' is subject/body
# typed by the rep and never reaches render_template.
BUILT_IN_TEMPLATES = ("information", "trial_information", "demo")


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


def render_template(
    key: str, *, contact_name: Optional[str], club_name: str, rep_name: str,
    calendly_url: Optional[str] = None,
) -> tuple[str, str, str]:
    """Returns (subject, html, text) for a BUILT_IN_TEMPLATES key. Raises
    ValueError for 'custom' or an unknown key — those have no template body,
    the caller supplies subject/text/html directly."""
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
    else:  # demo
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

    signoff_html = f'<p style="font-size:13px;color:#555;margin-top:24px">{rep_name}</p>'
    return subject, _wrap(subject, body + signoff_html), f"{text}\n\n{rep_name}"


def render_custom(subject: str, body_text: str, rep_name: str) -> tuple[str, str, str]:
    """A rep-typed subject/body wrapped in the same light HTML shell as the
    built-in templates — plain double-newline paragraphs, no rich editing
    (this is a quick note, not a campaign). The rep's raw text is HTML-escaped
    before embedding — free text typed into a form must never be trusted as
    markup, unlike this module's own hardcoded template strings above."""
    safe_subject = _html.escape(subject)
    paras = "".join(
        f'<p style="font-size:14px;line-height:1.5">{_html.escape(p).replace(chr(10), "<br>")}</p>'
        for p in body_text.split("\n\n") if p.strip()
    )
    signoff_html = f'<p style="font-size:13px;color:#555;margin-top:24px">{_html.escape(rep_name)}</p>'
    return safe_subject, _wrap(safe_subject, paras + signoff_html), f"{body_text}\n\n{rep_name}"


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
