from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.providers.base import ProviderError


async def activity_db(app, fn, *args, write=True, **kwargs):
    def run():
        if write and (Path(app.state.settings.material_storage_dir) / ".maintenance-lock").exists():
            raise ProviderError("maintenance", "学习数据维护中，请稍后重试", 503)
        return fn(app.state.session_factory, *args, **kwargs)

    if write and app.state.settings.database_url.startswith("sqlite"):
        async with app.state.sqlite_lock:
            return await run_in_threadpool(run)
    return await run_in_threadpool(run)
