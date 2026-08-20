"""Login, registration, logout, and current-user endpoints."""

from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    SESSION_HOURS,
    create_session,
    get_current_user,
    hash_password,
    validate_password_strength,
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
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        if value not in {"relationship_manager", "credit_analyst"}:
            raise ValueError("Role must be Relationship Manager or Credit Analyst.")
        return value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)


class ResetPasswordRequest(BaseModel):
    user_id: str = Field(min_length=3, max_length=64)
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not USER_ID_PATTERN.fullmatch(value):
            raise ValueError("Use only letters, numbers, periods, hyphens, or underscores.")
        return value


class UserResponse(BaseModel):
    user_id: str
    role: str


def _set_session_cookie(response: Response, raw_token: str, cookie_name: str) -> None:
    response.set_cookie(
        key=cookie_name,
        value=raw_token,
        max_age=SESSION_HOURS * 60 * 60,
        httponly=True,
        secure=settings.APP_ENV.lower() == "production",
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=UserResponse)
def login(
    credentials: Credentials,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.user_id == credentials.user_id).first()
    if not user or not user.is_active or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID or password.",
        )
    raw_token, _ = create_session(db, user)
    _set_session_cookie(response, raw_token, SESSION_COOKIE)
    return UserResponse(user_id=user.user_id, role=user.role)


@router.post("/register", response_model=UserResponse, status_code=201)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    try:
        validate_password_strength(request.password, request.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    existing = db.query(User).filter(User.user_id == request.user_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="That user ID is already registered.")

    user = User(
        user_id=request.user_id,
        password_hash=hash_password(request.password),
        role=request.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(user_id=user.user_id, role=user.role)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse(user_id=current_user.user_id, role=current_user.role)


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        raise HTTPException(status_code=401, detail="Your session is invalid.")
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match.")
    if verify_password(data.new_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different.")
    try:
        validate_password_strength(data.new_password, current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    current_user.password_hash = hash_password(data.new_password)
    current_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    db.query(AuthSession).filter(
        AuthSession.user_id == current_user.id,
        AuthSession.token_hash != current_hash,
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "Password changed successfully."}


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == data.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="User ID was not found.")
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match.")
    if verify_password(data.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different.")
    try:
        validate_password_strength(data.new_password, user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user.password_hash = hash_password(data.new_password)
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(
        synchronize_session=False
    )
    db.commit()
    return {"message": "Password reset successfully. You can now sign in."}


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    session_token = request.cookies.get(SESSION_COOKIE)
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
