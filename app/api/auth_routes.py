"""Login / logout / whoami."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..auth import (
    COOKIE_NAME,
    check_password,
    clear_failures,
    get_current_user,
    make_session,
    record_failure,
    too_many_failures,
)

router = APIRouter(prefix="/api", tags=["auth"])


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    ip = request.client.host if request.client else "unknown"
    if too_many_failures(ip):
        raise HTTPException(status_code=429, detail="Too many attempts; wait a minute")
    if not check_password(body.password):
        record_failure(ip)
        raise HTTPException(status_code=401, detail="Wrong password")
    clear_failures(ip)
    response.set_cookie(
        COOKIE_NAME,
        make_session(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(user: str = Depends(get_current_user)) -> dict:
    return {"user": user}
