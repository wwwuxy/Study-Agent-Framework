import logging
from pathlib import Path
from types import SimpleNamespace

from starlette.concurrency import run_in_threadpool

from app.chat.contracts import PreparedTurn
from app.chat.turns import fail_turn, prepare_turn, publish_turn
from app.core.orchestrator import get_adapter
from app.providers.base import ProviderError
from app.providers.invocation import PLANNING_PROMPT, invoke_structured
from app.schemas.chat import ChatDecision


async def db_phase(app, operation, *args, write=True, **kwargs):
    def run():
        if write and (Path(app.state.settings.material_storage_dir) / ".maintenance-lock").exists():
            raise ProviderError("maintenance", "学习数据维护中，请稍后重试", 503)
        return operation(app.state.session_factory, *args, **kwargs)

    if write and app.state.settings.database_url.startswith("sqlite"):
        async with app.state.sqlite_lock:
            return await run_in_threadpool(run)
    return await run_in_threadpool(run)


async def send_turn(app, session_hash, space_id, body):
    prepared = await db_phase(app, prepare_turn, session_hash, space_id, body)
    if not isinstance(prepared, PreparedTurn):
        return prepared
    call = None
    try:
        app.state.limiter.check("model:" + prepared.user_id, app.state.settings.provider_calls_per_minute)
        adapter = get_adapter(SimpleNamespace(app=app), prepared.provider_snapshot)
        call = await invoke_structured(adapter, ChatDecision, prepared.task, system_prompt=PLANNING_PROMPT)
        return await db_phase(app, publish_turn, prepared, call)
    except ProviderError as exc:
        return await db_phase(app, fail_turn, prepared, exc, call=call)
    except Exception as exc:
        logging.getLogger("uvicorn.error.study_agent").error("chat_failed type=%s", type(exc).__name__)
        return await db_phase(
            app, fail_turn, prepared, ProviderError("chat_failed", "处理未完成，原计划保持不变，可重试")
        )
