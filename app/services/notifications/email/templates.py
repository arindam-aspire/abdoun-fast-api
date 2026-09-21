from __future__ import annotations

import html
import re


def _otp_expiry_phrase(expiry_minutes: int) -> str:
    if expiry_minutes <= 0:
        return "This code has expired. Request a new verification code."
    if expiry_minutes == 1:
        return "This code will expire in 1 minute."
    return f"This code will expire in {expiry_minutes} minutes."


def text_to_html(text_body: str) -> str:
    """Convert a plain-text body into a simple HTML document."""
    escaped = html.escape(text_body)
    paragraphs = re.split(r"\n\s*\n", escaped.strip())
    html_paragraphs = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())
    return f"<html><body>{html_paragraphs}</body></html>"


def ensure_html_body(text_body: str, html_body: str | None) -> str:
    if html_body and html_body.strip():
        return html_body
    return text_to_html(text_body)


def build_otp_verification_email(
    *,
    app_name: str,
    otp: str,
    expiry_minutes: int,
    subject: str,
) -> tuple[str, str, str]:
    expiry_phrase = _otp_expiry_phrase(expiry_minutes)
    safe_app_name = html.escape(app_name)
    safe_otp = html.escape(otp)

    text_body = (
        f"{app_name}\n\n"
        f"Your verification code is:\n\n"
        f"{otp}\n\n"
        f"{expiry_phrase}\n\n"
        "Do not share this code with anyone."
    )
    html_body = (
        f"<html><body>"
        f"<p><strong>{safe_app_name}</strong></p>"
        f"<p>Your verification code is:</p>"
        f"<p style=\"font-size:24px;font-weight:bold;letter-spacing:2px;\">{safe_otp}</p>"
        f"<p>{html.escape(expiry_phrase)}</p>"
        f"<p>Do not share this code with anyone.</p>"
        f"</body></html>"
    )
    return subject, text_body, html_body
