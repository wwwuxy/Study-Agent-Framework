import time
from collections import defaultdict, deque

from fastapi import Depends, Request
from sqlalchemy import select

from app.core.security import token_hash
from app.db.models import AuthSession, ProviderConfig, StudySpace, User, as_utc, utcnow
from app.providers.base import ProviderError


class RateLimiter:
    def __init__(self):
        self.entries = defaultdict(deque)

    def check(self, key, limit):
        now = time.monotonic()
        # Remove expired keys as well as expired hits to bound anonymous traffic memory.
        if len(self.entries) > 5000:
            self.entries = defaultdict(
                deque, {k: v for k, v in self.entries.items() if v and v[-1] > now - 60}
            )
        hits = self.entries[key]
        while hits and hits[0] < now - 60:
            hits.popleft()
        if len(hits) >= limit:
            raise ProviderError("local_rate_limited", "请求过于频繁，请稍后重试", 429)
        hits.append(now)


async def get_db(request: Request):
    lock = request.app.state.sqlite_lock
    locked = request.method != "GET" and request.app.state.settings.database_url.startswith("sqlite")
    if locked:
        await lock.acquire()
    try:
        with request.app.state.session_factory() as db:
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
    finally:
        if locked:
            lock.release()


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get("study_session", "")
    session = db.get(AuthSession, token_hash(token)) if token else None
    if session is None or as_utc(session.expires_at) <= utcnow():
        raise ProviderError("unauthenticated", "请先登录", 401)
    query = select(User).where(User.id == session.user_id)
    if request.method != "GET":
        query = query.with_for_update()
    return db.scalar(query)


def own_provider(db, user_id, provider_id, require_tested=False):
    config = db.scalar(
        select(ProviderConfig).where(ProviderConfig.id == provider_id, ProviderConfig.user_id == user_id)
    )
    if not config:
        raise ProviderError("not_found", "模型配置不存在", 404)
    if require_tested and (not config.tested or not config.capabilities.get("chat")):
        raise ProviderError("provider_not_tested", "请先通过模型连接与能力检测", 422)
    return config


def own_space(db, user_id, space_id):
    space = db.scalar(select(StudySpace).where(StudySpace.id == space_id, StudySpace.user_id == user_id))
    if not space:
        raise ProviderError("not_found", "学习空间不存在", 404)
    return space
