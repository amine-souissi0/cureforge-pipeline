import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt

from app.orm_models import UserRow

_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "cureforge-dev-secret-change-in-prod")
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 12

_bearer_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
_apikey_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


# --- Password helpers ---

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# --- JWT helpers ---

def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire},
        _SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# --- FastAPI dependencies ---

async def get_current_user(
    token: Optional[str] = Depends(_bearer_scheme),
    api_key: Optional[str] = Security(_apikey_scheme),
) -> UserRow:
    """Accept either a JWT bearer token or the legacy X-API-Key header."""
    if token:
        payload = _decode_token(token)
        from app.services.user_store import UserStore
        user = await UserStore.get_by_id(payload["sub"])
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return user

    if api_key:
        expected = os.environ.get("API_KEY", "")
        if expected and api_key == expected:
            # Treat legacy API key as a synthetic admin user
            return UserRow(
                id="system",
                email="system@longevityintime.internal",
                name="System (API Key)",
                hashed_password="",
                role="admin",
                is_active=True,
                created_at=datetime.utcnow(),
            )
        raise HTTPException(status_code=403, detail="Invalid API key")

    raise HTTPException(status_code=401, detail="Authentication required")


async def require_admin(user: UserRow = Depends(get_current_user)) -> UserRow:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_recruiter(user: UserRow = Depends(get_current_user)) -> UserRow:
    """Any authenticated user (admin or recruiter)."""
    return user


# Alias used in main.py for global route protection
require_api_key = get_current_user
