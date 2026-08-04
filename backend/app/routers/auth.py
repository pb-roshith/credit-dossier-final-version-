"""Login, registration, logout, and current-user endpoints."""

from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    SESSION_HOURS,
    create_session,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models.user import AuthSession, User


router = APIRouter(prefix="/api/auth", tags=["authentication"])
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class Credentials(BaseModel):
    user_id: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not USER_ID_PATTERN.fullmatch(value):
            raise ValueError("Use only letters, numbers, periods, hyphens, or underscores.")
        return value


class RegisterRequest(Credentials):
    confirm_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    user_id: str
    role: str


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        max_age=SESSION_HOURS * 60 * 60,
        httponly=True,
        secure=settings.APP_ENV.lower() == "production",
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=UserResponse)
def login(credentials: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == credentials.user_id).first()
    if not user or not user.is_active or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID or password.",
        )
    raw_token, _ = create_session(db, user)
    _set_session_cookie(response, raw_token)
    return UserResponse(user_id=user.user_id, role=user.role)


@router.post("/register", response_model=UserResponse, status_code=201)
def register(request: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    existing = db.query(User).filter(User.user_id == request.user_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="That user ID is already registered.")

    user = User(
        user_id=request.user_id,
        password_hash=hash_password(request.password),
        role="normal",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    raw_token, _ = create_session(db, user)
    _set_session_cookie(response, raw_token)
    return UserResponse(user_id=user.user_id, role=user.role)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse(user_id=current_user.user_id, role=current_user.role)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
):
    if session_token:
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        auth_session = (
            db.query(AuthSession).filter(AuthSession.token_hash == token_hash).first()
        )
        if auth_session:
            db.delete(auth_session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    return Response(status_code=204, headers=response.headers)
