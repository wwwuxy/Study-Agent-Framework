import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select

from app.api.deps import current_user, get_db
from app.core.security import check_password, password_hash, token_hash
from app.db.models import AuthSession, User, utcnow
from app.providers.base import ProviderError
from app.schemas.api import Credentials

router = APIRouter(prefix="/auth", tags=["auth"])


def issue_session(request, response, db, user):
    token = secrets.token_urlsafe(40)
    ttl = request.app.state.settings.session_hours * 3600
    db.add(
        AuthSession(
            token_hash=token_hash(token), user_id=user.id, expires_at=utcnow() + timedelta(seconds=ttl)
        )
    )
    response.set_cookie(
        "study_session",
        token,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="strict",
        max_age=ttl,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"id": user.id, "username": user.username, "timezone": user.timezone}


@router.post("/register", status_code=201)
async def register(body: Credentials, request: Request, response: Response, db=Depends(get_db)):
    request.app.state.limiter.check("auth:" + request.client.host, 10)
    username = body.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise ProviderError("username_taken", "用户名已存在", 409)
    user = User(username=username, password_hash=password_hash(body.password.get_secret_value()))
    db.add(user)
    db.flush()
    return issue_session(request, response, db, user)


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response, db=Depends(get_db)):
    request.app.state.limiter.check("auth:" + request.client.host, 10)
    user = db.scalar(select(User).where(User.username == body.username.lower()))
    # Spend the same password KDF even for an unknown account.
    stored = user.password_hash if user else request.app.state.dummy_password_hash
    valid = check_password(body.password.get_secret_value(), stored)
    if not user or not valid:
        raise ProviderError("invalid_credentials", "用户名或密码错误", 401)
    return issue_session(request, response, db, user)


@router.get("/me")
async def me(user=Depends(current_user)):
    return {"id": user.id, "username": user.username, "timezone": user.timezone}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db=Depends(get_db)):
    token = request.cookies.get("study_session", "")
    db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    response.delete_cookie("study_session", path="/")
