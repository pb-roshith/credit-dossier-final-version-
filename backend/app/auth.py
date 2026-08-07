"""Password hashing, session creation, and FastAPI authorization dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import re
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import AuthSession, User


SESSION_COOKIE = "credit_dossier_session"
FRONTEND_SESSION_COOKIES = {
    "frontend": "credit_dossier_session_frontend",
    "frontend_2": "credit_dossier_session_frontend_2",
}
FRONTEND_HEADER = "x-credit-dossier-frontend"
SESSION_HOURS = 12
PBKDF2_ITERATIONS = 600_000
ALLOWED_ROLES = {"relationship_manager", "credit_analyst"}


def session_cookie_name(request: Request) -> str:
    """Use independent cookies for the two localhost frontend applications."""
    frontend_id = request.headers.get(FRONTEND_HEADER, "").strip().lower()
    return FRONTEND_SESSION_COOKIES.get(frontend_id, SESSION_COOKIE)


def validate_password_strength(password: str, user_id: str | None = None) -> None:
    """Enforce the password policy for registration and password changes."""
    requirements = []
    if len(password) < 12:
        requirements.append("at least 12 characters")
    if not re.search(r"[A-Z]", password):
        requirements.append("one uppercase letter")
    if not re.search(r"[a-z]", password):
        requirements.append("one lowercase letter")
    if not re.search(r"\d", password):
        requirements.append("one number")
    if not re.search(r"[^A-Za-z0-9]", password):
        requirements.append("one special character")
    if user_id and user_id.lower() in password.lower():
        requirements.append("a password that does not contain the user ID")
    if requirements:
        raise ValueError("Password must contain " + ", ".join(requirements) + ".")


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
    """Create initial role accounts and migrate legacy role names."""
    from app.config import settings

    accounts = (
        (
            settings.INITIAL_RELATIONSHIP_MANAGER_USER_ID,
            settings.INITIAL_RELATIONSHIP_MANAGER_PASSWORD,
            "relationship_manager",
        ),
        (
            settings.INITIAL_CREDIT_ANALYST_USER_ID,
            settings.INITIAL_CREDIT_ANALYST_PASSWORD,
            "credit_analyst",
        ),
    )
    changed = False
    for configured_user_id, password, role in accounts:
        user_id = configured_user_id.strip().lower()
        if not user_id or not password:
            continue
        if db.query(User).filter(User.user_id == user_id).first():
            continue
        validate_password_strength(password, user_id)
        db.add(User(user_id=user_id, password_hash=hash_password(password), role=role))
        changed = True
    changed = bool(
        db.query(User).filter(User.role == "admin").update(
            {User.role: "relationship_manager"}, synchronize_session=False
        )
    ) or changed
    changed = bool(
        db.query(User).filter(User.role == "normal").update(
            {User.role: "credit_analyst"}, synchronize_session=False
        )
    ) or changed
    if changed:
        db.commit()


def _unauthorized(detail: str = "Please sign in to continue.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    session_token = request.cookies.get(session_cookie_name(request))
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


def require_deal_owner(
    deal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allow an RM to access owned deals and a Credit Analyst to access all deals."""
    from app.models.deal import Deal

    query = db.query(Deal).filter(Deal.id == deal_id)
    if current_user.role == "relationship_manager":
        query = query.filter(Deal.owner_user_id == current_user.id)
    elif current_user.role != "credit_analyst":
        raise HTTPException(status_code=403, detail="Your role cannot access deals.")
    deal = query.first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found.")
    return deal


def require_relationship_manager(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "relationship_manager":
        raise HTTPException(
            status_code=403,
            detail="Only Relationship Managers can create or submit deals.",
        )
    return current_user


def require_credit_analyst(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "credit_analyst":
        raise HTTPException(
            status_code=403,
            detail="Only Credit Analysts can approve deals.",
        )
    return current_user
