import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import (
    create_access_token,
    hash_password,
    require_admin,
    verify_password,
    get_current_user,
)
from app.orm_models import UserRow
from app.services.user_store import UserStore

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str = "recruiter"  # "admin" | "recruiter"


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_active: bool


def _user_out(u: UserRow) -> UserOut:
    return UserOut(id=u.id, email=u.email, name=u.name, role=u.role, is_active=u.is_active)


@router.post("/login")
async def login(payload: LoginRequest) -> dict:
    user = await UserStore.get_by_email(payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_access_token(user.id, user.role)
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user).model_dump()}


@router.get("/me")
async def me(user: UserRow = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


@router.post("/register")
async def register(
    payload: RegisterRequest,
    _admin: UserRow = Depends(require_admin),
) -> UserOut:
    if payload.role not in ("admin", "recruiter"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'recruiter'")
    existing = await UserStore.get_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = await UserStore.create(
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    return _user_out(user)


@router.get("/users")
async def list_users(_admin: UserRow = Depends(require_admin)) -> List[UserOut]:
    users = await UserStore.list_all()
    return [_user_out(u) for u in users]


@router.patch("/users/{user_id}/activate")
async def activate_user(user_id: str, _admin: UserRow = Depends(require_admin)) -> UserOut:
    user = await UserStore.set_active(user_id, True)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_out(user)


@router.patch("/users/{user_id}/deactivate")
async def deactivate_user(user_id: str, current: UserRow = Depends(require_admin)) -> UserOut:
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    user = await UserStore.set_active(user_id, False)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_out(user)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, current: UserRow = Depends(require_admin)) -> dict:
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    deleted = await UserStore.delete(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"deleted": True}
