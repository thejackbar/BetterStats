"""Allow-list HTML sanitiser for club-authored website content.

Website copy (news articles, info pages, the homepage intro) is written by
authenticated club admins through the WYSIWYG editor, but we still sanitise on
save so a malicious/compromised admin can't store script that would run for
that club's public visitors (stored XSS). Dependency-free — built on the stdlib
``HTMLParser`` with a strict tag/attribute allow-list. Anything not on the list
is dropped (the tag is removed but its text is kept); ``<script>``/``<style>``
and friends have their *contents* dropped too.
"""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

# Tags we keep. Everything a club needs for prose, no layout/scripting.
ALLOWED_TAGS = {
    "p", "br", "hr", "div",
    "h2", "h3", "h4",
    "strong", "b", "em", "i", "u", "s", "strike",
    "ul", "ol", "li",
    "blockquote", "a", "img",
    "span", "figure", "figcaption", "code", "pre",
}

# Tags whose entire subtree is discarded (not just the tag).
FORBIDDEN_CONTENT_TAGS = {
    "script", "style", "iframe", "object", "embed",
    "noscript", "template", "form", "input", "textarea", "button", "svg",
}

# Self-closing / void elements — never get a closing tag.
VOID_TAGS = {"br", "hr", "img"}

# Per-tag attribute allow-list. Anything not listed here is stripped, so
# class/style/on*-handlers never survive.
ALLOWED_ATTRS = {
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title", "width", "height"},
}

SAFE_URL_SCHEMES = {"http", "https", "mailto", "tel"}

_CTRL = re.compile(r"[\x00-\x20]+")
_SCHEME = re.compile(r"^([a-z][a-z0-9+.\-]*):")

MAX_HTML_LEN = 200_000


def _url_scheme(value: str) -> str:
    """Return the URL scheme, or "relative" for scheme-less/anchor URLs.

    Strips control characters and whitespace first so tricks like
    ``java\\tscript:`` or a leading newline can't smuggle a scheme past us.
    """
    compact = _CTRL.sub("", value or "").lower()
    if compact.startswith(("/", "#", "./", "../", "?")):
        return "relative"
    m = _SCHEME.match(compact)
    return m.group(1) if m else "relative"


def _is_safe_url(value: str, *, image: bool = False) -> bool:
    scheme = _url_scheme(value)
    if scheme == "relative":
        return True
    if scheme not in SAFE_URL_SCHEMES:
        return False
    # Images can only point at real http(s)/relative resources.
    if image and scheme not in ("http", "https"):
        return False
    return True


class _Sanitiser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open_stack: list[str] = []  # allowed non-void tags we've opened
        self.skip_depth = 0              # >0 while inside a forbidden subtree

    # ── tags ────────────────────────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        if self.skip_depth:
            if tag in FORBIDDEN_CONTENT_TAGS:
                self.skip_depth += 1
            return
        if tag in FORBIDDEN_CONTENT_TAGS:
            self.skip_depth = 1
            return
        if tag not in ALLOWED_TAGS:
            return  # drop the tag, keep its children
        attr_str = self._clean_attrs(tag, attrs)
        self.out.append(f"<{tag}{attr_str}>")
        if tag not in VOID_TAGS:
            self.open_stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if self.skip_depth or tag in FORBIDDEN_CONTENT_TAGS or tag not in ALLOWED_TAGS:
            return
        attr_str = self._clean_attrs(tag, attrs)
        self.out.append(f"<{tag}{attr_str}>")  # always treat as void here

    def handle_endtag(self, tag):
        if self.skip_depth:
            if tag in FORBIDDEN_CONTENT_TAGS:
                self.skip_depth -= 1
            return
        if tag in VOID_TAGS or tag not in ALLOWED_TAGS:
            return
        if tag not in self.open_stack:
            return  # stray close — ignore
        # Close down to (and including) the matching open tag.
        while self.open_stack:
            t = self.open_stack.pop()
            self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.out.append(escape(data, quote=False))

    # Comments / declarations / processing-instructions are all dropped (the
    # base class no-ops them and we don't override to emit anything).

    # ── attributes ────────────────────────────────────────────────────────────
    def _clean_attrs(self, tag, attrs) -> str:
        allowed = ALLOWED_ATTRS.get(tag, set())
        parts: list[str] = []
        seen: set[str] = set()
        has_blank_target = False
        for name, value in attrs:
            name = (name or "").lower()
            if name in seen or name not in allowed:
                continue
            value = value or ""
            if name in ("href", "src"):
                if not _is_safe_url(value, image=(name == "src")):
                    continue
            if name == "target":
                value = "_blank"
                has_blank_target = True
            parts.append(f' {name}="{escape(value, quote=True)}"')
            seen.add(name)
        # Anchors that open a new tab must not leak window.opener.
        if tag == "a" and has_blank_target and "rel" not in seen:
            parts.append(' rel="noopener noreferrer"')
        return "".join(parts)

    def close_all(self) -> None:
        while self.open_stack:
            self.out.append(f"</{self.open_stack.pop()}>")


def sanitize_html(raw: str | None) -> str:
    """Return a safe HTML string built from an allow-list of tags/attributes."""
    if not raw:
        return ""
    parser = _Sanitiser()
    parser.feed(raw[:MAX_HTML_LEN])
    parser.close()
    parser.close_all()
    return "".join(parser.out)


def html_to_text(raw: str | None, limit: int = 280) -> str:
    """Strip all tags to plain text — used to auto-derive a news summary."""
    if not raw:
        return ""

    chunks: list[str] = []
    _BLOCK = {"p", "br", "hr", "h2", "h3", "h4", "li", "ul", "ol", "blockquote", "figure", "figcaption", "div", "tr"}

    class _Stripper(HTMLParser):
        def handle_data(self, data):
            chunks.append(data)

        def handle_starttag(self, tag, attrs):
            if tag in _BLOCK:
                chunks.append(" ")

        def handle_endtag(self, tag):
            if tag in _BLOCK:
                chunks.append(" ")

    stripper = _Stripper()
    stripper.feed(raw[:MAX_HTML_LEN])
    stripper.close()
    text = re.sub(r"\s+", " ", "".join(chunks)).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip() + "…"
    return text
