"""Shared password strength rule, used everywhere a user sets their own
password outside the super-admin "just set it for them" tools: self-serve
trial registration (routers/self_serve_trial.py) and the club-user invite
accept flow (routers/auth.py). One rule, one place, so the two flows can
never drift apart."""
import re

MIN_LEN = 10
_HAS_UPPER = re.compile(r"[A-Z]")
_HAS_DIGIT = re.compile(r"\d")
_HAS_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def password_errors(password: str, confirm: str) -> list[str]:
    errors = []
    if len(password or "") < MIN_LEN:
        errors.append(f"Password must be at least {MIN_LEN} characters")
    if not _HAS_UPPER.search(password or ""):
        errors.append("Password must contain an uppercase letter")
    if not _HAS_DIGIT.search(password or ""):
        errors.append("Password must contain a number")
    if not _HAS_SPECIAL.search(password or ""):
        errors.append("Password must contain a special character")
    if password != confirm:
        errors.append("Passwords do not match")
    return errors
