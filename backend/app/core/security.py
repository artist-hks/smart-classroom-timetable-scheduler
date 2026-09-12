"""
Password hashing + JWT helpers — SB2/US7/T1.

Kept deliberately free of any DB/FastAPI imports so it's trivially unit
testable and reusable from CLI scripts (e.g. the admin-bootstrap script).
"""

from __future__ import annotations

import datetime
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_token(
    *,
    subject: str,
    token_type: TokenType,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    subject: the user_id as a string (JWT `sub` claim must be a string).
    token_type: "access" or "refresh" — encoded as a `type` claim so
    /auth/refresh can reject an access token used where a refresh token
    is expected, and vice versa.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    if token_type == "access":
        expire = now + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    else:
        expire = now + datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Raises jwt.PyJWTError (or a subclass, e.g. jwt.ExpiredSignatureError,
    jwt.InvalidTokenError) on any problem — callers convert that to a 401.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
