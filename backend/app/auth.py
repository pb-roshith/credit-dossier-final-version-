"""Password hashing, session creation, and FastAPI authorization dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import AuthSession, User


SESSION_COOKIE = "credit_dossier_session"
SESSION_HOURS = 12
PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_session(db: Session, user: User) -> tuple[str, AuthSession]:
    raw_token = secrets.token_urlsafe(48)
    session = AuthSession(
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS),
    )
    db.add(session)
    db.commit()
    return raw_token, session


def seed_initial_users(db: Session) -> None:
    """Create the configured local admin and normal accounts once."""
    from app.config import settings

    accounts = (
        (settings.INITIAL_ADMIN_USER_ID, settings.INITIAL_ADMIN_PASSWORD, "admin"),
        (settings.INITIAL_NORMAL_USER_ID, settings.INITIAL_NORMAL_PASSWORD, "normal"),
    )
    changed = False
    for configured_user_id, password, role in accounts:
        user_id = configured_user_id.strip().lower()
        if not user_id or not password:
            continue
        if db.query(User).filter(User.user_id == user_id).first():
            continue
        db.add(User(user_id=user_id, password_hash=hash_password(password), role=role))
        changed = True
    if changed:
        db.commit()


def _unauthorized(detail: str = "Please sign in to continue.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    if not session_token:
        raise _unauthorized()

    token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    auth_session = (
        db.query(AuthSession).filter(AuthSession.token_hash == token_hash).first()
    )
    if not auth_session:
        raise _unauthorized("Your session is invalid. Please sign in again.")

    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        db.delete(auth_session)
        db.commit()
        raise _unauthorized("Your session has expired. Please sign in again.")

    user = auth_session.user
    if not user or not user.is_active:
        raise _unauthorized("This user account is inactive.")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required for Manufacture Data.",
        )
    return current_user
