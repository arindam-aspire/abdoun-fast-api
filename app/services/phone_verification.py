"""Phone verification OTP flow.

Verification codes are stored as hashes, sent only to the number already
stored for the user, and never returned to callers. Signup confirmation can
verify the mobile code on its own or together with the email code.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.live_schema import User, UserProfileChangeChallenge
from app.services.auth import (
    SIGNUP_EMAIL_PURPOSE,
    create_otp_challenge,
    get_user_or_404,
    otp_remaining_minutes,
    utc_now,
    verify_otp_challenge,
)
from app.services.notifications import send_sms_notification
from app.services.notifications.email.templates import build_otp_verification_sms
from app.services.notifications.sms import mask_phone, to_e164_phone
from app.utils.status_codes import (
    STATUS_BAD_REQUEST,
    STATUS_CONFLICT,
    STATUS_NOT_FOUND,
    STATUS_SERVICE_UNAVAILABLE,
    STATUS_TOO_MANY_REQUESTS,
)

logger = logging.getLogger(__name__)

PHONE_VERIFY_PURPOSE = "phone_verify"
PROFILE_PHONE_PURPOSE = "profile_phone"
_PHONE_PURPOSES = (PHONE_VERIFY_PURPOSE, PROFILE_PHONE_PURPOSE)


def require_phone_number(phone_number: str | None) -> str:
    normalized = to_e164_phone(phone_number)
    if not normalized:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Invalid phone number")
    return normalized


def prepare_signup_phone(
    db: Session,
    phone_number: str | None,
    *,
    exclude_user_id: UUID | None = None,
) -> str | None:
    """Normalize an optional signup phone and reject duplicates.

    A missing phone stays optional. A supplied phone is stored unverified by
    the caller; this function does not mark it verified.
    """
    if phone_number is None or not str(phone_number).strip():
        return None
    normalized = require_phone_number(phone_number)
    assert_phone_available(db, normalized, exclude_user_id=exclude_user_id)
    return normalized


def assert_phone_available(db: Session, phone: str, *, exclude_user_id: UUID | None) -> None:
    existing = find_user_by_phone(db, phone)
    if existing and existing.id != exclude_user_id:
        raise HTTPException(
            status_code=STATUS_CONFLICT,
            detail="An account with this phone number already exists",
        )


def find_user_by_phone(db: Session, phone: str) -> User | None:
    normalized = to_e164_phone(phone)
    if not normalized:
        return None
    return db.execute(select(User).where(User.phone_number == normalized)).scalars().first()


def request_phone_otp(
    db: Session,
    *,
    user_id: UUID | None,
    phone_number: str | None,
) -> tuple[dict[str, object], str]:
    user, phone = resolve_phone_otp_subject(db, user_id=user_id, phone_number=phone_number)
    if user.is_phone_verified is True:
        return {"phone_verified": True}, "Mobile number is already verified"
    issue_phone_verification_otp(
        db,
        user=user,
        phone=phone,
        purpose=PHONE_VERIFY_PURPOSE,
        enforce_cooldown=True,
        require_delivery=True,
    )
    return {"phone_verified": False}, "Verification code sent."


def confirm_signup_phone_otp(
    db: Session,
    *,
    user: User,
    phone_number: str | None,
    phone_otp: str,
) -> User:
    """Verify the signup mobile OTP for the number already stored on the user."""
    registered = to_e164_phone(user.phone_number if isinstance(user.phone_number, str) else None)
    if not registered:
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Phone number is missing")
    if phone_number is not None and str(phone_number).strip():
        requested = require_phone_number(phone_number)
        if requested != registered:
            raise HTTPException(
                status_code=STATUS_BAD_REQUEST,
                detail="Phone number does not match the registered mobile number",
            )
    if user.is_phone_verified is True:
        return user
    verify_otp_challenge(
        db,
        purpose=PHONE_VERIFY_PURPOSE,
        code=phone_otp,
        user=user,
        new_value=registered,
    )
    user.is_phone_verified = True
    db.flush()
    return user


def confirm_phone_otp(
    db: Session,
    *,
    user_id: UUID | None,
    phone_number: str,
    phone_otp: str,
) -> User:
    user, phone = resolve_phone_otp_subject(db, user_id=user_id, phone_number=phone_number)
    if user.is_phone_verified is True:
        return user
    verify_otp_challenge(
        db,
        purpose=PHONE_VERIFY_PURPOSE,
        code=phone_otp,
        user=user,
        new_value=phone,
    )
    user.is_phone_verified = True
    db.flush()
    return user


def apply_profile_phone_number(db: Session, *, user: User, phone_number: str) -> None:
    """Store a profile phone immediately and require a new verification."""
    if not str(phone_number).strip():
        user.phone_number = None
        user.is_phone_verified = False
        _invalidate_open_challenges(db, user_id=user.id, purposes=_PHONE_PURPOSES)
        return

    normalized = require_phone_number(phone_number)
    current = to_e164_phone(user.phone_number if isinstance(user.phone_number, str) else None)
    if current == normalized and user.is_phone_verified is True:
        return
    assert_phone_available(db, normalized, exclude_user_id=user.id)
    user.phone_number = normalized
    user.is_phone_verified = False
    _invalidate_open_challenges(db, user_id=user.id, purposes=_PHONE_PURPOSES)
    issue_phone_verification_otp(
        db,
        user=user,
        phone=normalized,
        purpose=PHONE_VERIFY_PURPOSE,
        enforce_cooldown=False,
        require_delivery=False,
    )


def begin_profile_phone_change(db: Session, *, user: User, phone_number: str) -> bool:
    """Send an OTP for a pending phone change without applying it yet.

    Returns False when the current number is already verified and unchanged.
    """
    normalized = require_phone_number(phone_number)
    current = to_e164_phone(user.phone_number if isinstance(user.phone_number, str) else None)
    if current == normalized and user.is_phone_verified is True:
        return False
    assert_phone_available(db, normalized, exclude_user_id=user.id)
    issue_phone_verification_otp(
        db,
        user=user,
        phone=normalized,
        purpose=PROFILE_PHONE_PURPOSE,
        enforce_cooldown=True,
        require_delivery=True,
    )
    return True


def complete_profile_phone_verification(
    db: Session,
    *,
    user: User,
    phone_number: str,
    phone_otp: str,
) -> None:
    normalized = require_phone_number(phone_number)
    verified_phone = _consume_profile_phone_otp(
        db,
        user=user,
        phone_number=normalized,
        phone_otp=phone_otp,
    )
    assert_phone_available(db, verified_phone, exclude_user_id=user.id)
    user.phone_number = verified_phone
    user.is_phone_verified = True
    _invalidate_open_challenges(db, user_id=user.id, purposes=(PHONE_VERIFY_PURPOSE,))


def _consume_profile_phone_otp(
    db: Session,
    *,
    user: User,
    phone_number: str,
    phone_otp: str,
) -> str:
    """Return the number the OTP was sent to.

    Profile verify often resubmits the number already saved on the user while
    the open challenge belongs to the pending replacement. The code is checked
    against that pending number, and that number is the one marked verified.
    """
    try:
        verify_otp_challenge(
            db,
            purpose=PROFILE_PHONE_PURPOSE,
            code=phone_otp,
            user=user,
            new_value=phone_number,
        )
        return phone_number
    except HTTPException as exc:
        if exc.status_code != STATUS_BAD_REQUEST or exc.detail != "Verification code not found":
            raise

    challenge = _latest_open_challenge(db, user_id=user.id, purpose=PROFILE_PHONE_PURPOSE)
    pending = challenge.new_value if challenge is not None and isinstance(challenge.new_value, str) else ""
    current = to_e164_phone(user.phone_number if isinstance(user.phone_number, str) else None)
    if challenge is None or not pending or not _pending_phone_matches(phone_number, current, pending):
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Verification code not found")

    verify_otp_challenge(
        db,
        purpose=PROFILE_PHONE_PURPOSE,
        code=phone_otp,
        user=user,
        challenge_id=challenge.id,
    )
    return pending


def _pending_phone_matches(submitted: str, current: str | None, pending: str) -> bool:
    if submitted == pending:
        return True
    if current and submitted == current:
        return True
    return submitted.startswith(pending) or pending.startswith(submitted)


def issue_signup_phone_otp(
    db: Session,
    *,
    user: User,
    excluded_otps: set[str] | None = None,
) -> None:
    phone = user.phone_number if isinstance(user.phone_number, str) else None
    if not phone or not phone.strip() or user.is_phone_verified is True:
        return
    delivered = issue_phone_verification_otp(
        db,
        user=user,
        phone=require_phone_number(phone),
        purpose=PHONE_VERIFY_PURPOSE,
        enforce_cooldown=True,
        require_delivery=False,
        excluded_otps=excluded_otps,
        avoid_purposes=(SIGNUP_EMAIL_PURPOSE,),
    )
    if delivered:
        logger.info("Signup phone OTP generated successfully for user %s", user.id)


def issue_phone_verification_otp(
    db: Session,
    *,
    user: User,
    phone: str,
    purpose: str,
    enforce_cooldown: bool,
    require_delivery: bool,
    excluded_otps: set[str] | None = None,
    avoid_purposes: tuple[str, ...] = (),
) -> bool:
    settings = get_settings()
    latest = _latest_otp_challenge(db, user_id=user.id, purpose=purpose)
    if enforce_cooldown and _within_cooldown(latest, settings.auth_otp_resend_cooldown_seconds):
        raise HTTPException(
            status_code=STATUS_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another verification code",
        )
    window_start = utc_now() - timedelta(seconds=max(settings.auth_otp_send_window_seconds, 1))
    sent_count = _count_recent_otp_challenges(db, user_id=user.id, purpose=purpose, since=window_start)
    if sent_count >= max(settings.auth_otp_max_sends_per_window, 1):
        raise HTTPException(
            status_code=STATUS_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Please try again later",
        )

    _invalidate_open_challenges(db, user_id=user.id, purposes=(purpose,))
    challenge, otp = create_otp_challenge(
        db,
        user=user,
        purpose=purpose,
        new_value=phone,
        excluded_otps=excluded_otps,
        avoid_purposes=avoid_purposes,
    )
    delivered = _deliver_phone_otp(phone=phone, otp=otp, challenge=challenge)
    if delivered:
        return True
    challenge.consumed_at = utc_now()
    db.flush()
    logger.warning("phone_otp_not_delivered to=%s", mask_phone(phone))
    if require_delivery:
        raise HTTPException(
            status_code=STATUS_SERVICE_UNAVAILABLE,
            detail="Unable to send verification code",
        )
    return False


def resolve_phone_otp_subject(
    db: Session,
    *,
    user_id: UUID | None,
    phone_number: str | None,
) -> tuple[User, str]:
    """Resolve the stored phone. Never substitute a caller-supplied destination."""
    if user_id is not None:
        user = get_user_or_404(db, user_id)
        registered = to_e164_phone(user.phone_number if isinstance(user.phone_number, str) else None)
        if not registered:
            raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Phone number is missing")
        if phone_number is not None and str(phone_number).strip():
            requested = require_phone_number(phone_number)
            if requested != registered:
                raise HTTPException(
                    status_code=STATUS_BAD_REQUEST,
                    detail="Phone number does not match the registered mobile number",
                )
        return user, registered

    if phone_number is None or not str(phone_number).strip():
        raise HTTPException(status_code=STATUS_BAD_REQUEST, detail="Phone number is required")
    requested = require_phone_number(phone_number)
    user = find_user_by_phone(db, requested)
    if not user:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail="Account not found")
    registered = to_e164_phone(user.phone_number if isinstance(user.phone_number, str) else None)
    if registered != requested:
        raise HTTPException(
            status_code=STATUS_BAD_REQUEST,
            detail="Phone number does not match the registered mobile number",
        )
    return user, registered


def _deliver_phone_otp(*, phone: str, otp: str, challenge: UserProfileChangeChallenge) -> bool:
    settings = get_settings()
    expiry_minutes = otp_remaining_minutes(challenge.expires_at)
    if expiry_minutes <= 0:
        expiry_minutes = max(settings.auth_otp_ttl_seconds // 60, 1)
    try:
        return send_sms_notification(
            to_phone=phone,
            body=build_otp_verification_sms(
                app_name=settings.app_name,
                otp=otp,
                expiry_minutes=expiry_minutes,
            ),
        )
    except Exception as exc:
        logger.warning("otp_sms_send_failed purpose=%s error_type=%s", PHONE_VERIFY_PURPOSE, type(exc).__name__)
        return False


def _latest_open_challenge(db: Session, *, user_id: UUID, purpose: str) -> UserProfileChangeChallenge | None:
    challenge = db.execute(
        select(UserProfileChangeChallenge)
        .where(
            UserProfileChangeChallenge.user_id == user_id,
            UserProfileChangeChallenge.purpose == purpose,
            UserProfileChangeChallenge.consumed_at.is_(None),
        )
        .order_by(UserProfileChangeChallenge.created_at.desc())
    ).scalars().first()
    return challenge if isinstance(challenge, UserProfileChangeChallenge) else None


def _latest_otp_challenge(db: Session, *, user_id: UUID, purpose: str) -> UserProfileChangeChallenge | None:
    return db.execute(
        select(UserProfileChangeChallenge)
        .where(
            UserProfileChangeChallenge.user_id == user_id,
            UserProfileChangeChallenge.purpose == purpose,
        )
        .order_by(UserProfileChangeChallenge.created_at.desc())
    ).scalars().first()


def _count_recent_otp_challenges(db: Session, *, user_id: UUID, purpose: str, since: datetime) -> int:
    count = db.execute(
        select(func.count())
        .select_from(UserProfileChangeChallenge)
        .where(
            UserProfileChangeChallenge.user_id == user_id,
            UserProfileChangeChallenge.purpose == purpose,
            UserProfileChangeChallenge.created_at >= since,
        )
    ).scalar()
    return int(count or 0)


def _invalidate_open_challenges(db: Session, *, user_id: UUID, purposes: tuple[str, ...]) -> None:
    rows = db.execute(
        select(UserProfileChangeChallenge).where(
            UserProfileChangeChallenge.user_id == user_id,
            UserProfileChangeChallenge.purpose.in_(purposes),
            UserProfileChangeChallenge.consumed_at.is_(None),
        )
    ).scalars().all()
    now = utc_now()
    for row in rows:
        row.consumed_at = now
    if rows:
        db.flush()


def _within_cooldown(challenge: UserProfileChangeChallenge | None, cooldown_seconds: int) -> bool:
    if challenge is None or challenge.consumed_at is not None or challenge.created_at is None:
        return False
    created_at = challenge.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed = (utc_now() - created_at).total_seconds()
    return elapsed < cooldown_seconds
