# readex/backend/main.py
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import settings
from database import Base, engine, SessionLocal
import models  # noqa: F401
from routers import series, search, downloads, schedules, settings as settings_router, import_library, proxy
from services.download_service import DownloadService
from services.download_worker import DownloadWorker
from services.library_scanner import LibraryScanner
from services.scheduler_service import SchedulerService
from sources.registry import SourceRegistry
from sources.mangadex import MangaDexSource
from sources.asurascans import AsuraScansSource
from sources.weebcentral import WeebCentralSource
from sources.mangapill import MangaPillSource
from sources.mangakatana import MangaKatanaSource
from sources.getcomics import GetComicsSource
from sources.readcomiconline import ReadComicOnlineSource


@asynccontextmanager
def _ensure_schema():
    """Lightweight migrations: add columns SQLAlchemy create_all would skip."""
    from sqlalchemy import text
    with engine.connect() as conn:
        for col, ddl in [
            ("progress_current", "ALTER TABLE download_queue ADD COLUMN progress_current INTEGER NOT NULL DEFAULT 0"),
            ("progress_total",   "ALTER TABLE download_queue ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass  # column already exists


def _recover_stuck_jobs():
    """Reset queue entries left in 'active' / chapters in 'downloading' from a prior crash."""
    from models import DownloadQueue, Chapter
    db = SessionLocal()
    try:
        stuck_q = db.query(DownloadQueue).filter_by(status="active").all()
        for e in stuck_q:
            e.status = "pending"
            e.progress_current = 0
            e.progress_total = 0
            ch = db.get(Chapter, e.chapter_id)
            if ch and ch.status == "downloading":
                ch.status = "queued"
        if stuck_q:
            db.commit()
        # Also catch chapters left "downloading" with no queue entry
        orphans = db.query(Chapter).filter_by(status="downloading").all()
        for ch in orphans:
            ch.status = "queued"
        if orphans:
            db.commit()
    finally:
        db.close()


async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_schema()
    _recover_stuck_jobs()
    from routers.settings import apply_overrides_on_startup
    apply_overrides_on_startup()

    registry = SourceRegistry()
    for source_cls in [
        MangaDexSource, AsuraScansSource,
        WeebCentralSource, MangaPillSource, MangaKatanaSource,
        GetComicsSource, ReadComicOnlineSource,
    ]:
        registry.register(source_cls())
    app.state.source_registry = registry

    download_service = DownloadService(library_path=settings.library_path)
    app.state.download_service = download_service

    # Library scan on startup
    db = SessionLocal()
    try:
        scanner = LibraryScanner(library_path=settings.library_path)
        scanner.scan(db)
    except Exception as e:
        import logging
        logging.getLogger("readex").warning(f"Library scan failed (ok on first run): {e}")
    finally:
        db.close()

    # Background download worker
    worker = DownloadWorker(
        db_factory=SessionLocal,
        registry=registry,
        download_service=download_service,
        max_concurrent=settings.concurrent_downloads,
    )
    worker_task = asyncio.create_task(worker.start())

    # Scheduler
    from datetime import datetime
    from models import Schedule, Series, Chapter, DownloadQueue

    def _check_series(series_id: int) -> None:
        """Fetch the source's chapter list and queue any new chapters."""
        import asyncio as _asyncio
        import logging
        log = logging.getLogger("readex.scheduler")
        s = SessionLocal()
        try:
            series = s.get(Series, series_id)
            if not series:
                return
            sched = s.query(Schedule).filter_by(series_id=series_id).first()
            source = registry.get(series.source_name)
            if source is None:
                log.warning(f"scheduled check skipped — unknown source {series.source_name}")
                return
            try:
                ch_list = _asyncio.run(source.check_updates(series.source_id))
            except Exception as e:
                log.warning(f"scheduled check failed for series {series_id}: {e}")
                if sched:
                    sched.last_checked_at = datetime.utcnow()
                    s.commit()
                return

            existing_ids = {
                ch.source_chapter_id for ch in
                s.query(Chapter).filter_by(series_id=series.id).all()
            }
            added = 0
            for ch_info in ch_list:
                if ch_info.source_chapter_id in existing_ids:
                    continue
                new_ch = Chapter(
                    series_id=series.id,
                    chapter_number=ch_info.chapter_number,
                    title=ch_info.title,
                    source_chapter_id=ch_info.source_chapter_id,
                    source_chapter_url=ch_info.url or None,
                    status="queued",
                )
                s.add(new_ch)
                s.flush()
                s.add(DownloadQueue(
                    chapter_id=new_ch.id, priority=0, status="pending", retries=0,
                ))
                added += 1
            if sched:
                from datetime import timedelta
                now = datetime.utcnow()
                sched.last_checked_at = now
                sched.next_check_at = now + timedelta(seconds=sched.interval_seconds)
            s.commit()
            if added > 0:
                log.info(f"series {series_id} ({series.title}) — queued {added} new chapter(s)")
        except Exception:
            log.exception("scheduled check crashed")
        finally:
            s.close()

    scheduler = SchedulerService(check_func=_check_series)
    scheduler.start()
    app.state.scheduler = scheduler

    # Load all enabled schedules from DB so they survive container restarts
    db = SessionLocal()
    try:
        from datetime import timedelta
        now = datetime.utcnow()
        for sch in db.query(Schedule).filter_by(enabled=True).all():
            scheduler.add_job(sch.series_id, sch.interval_seconds)
            # Estimate next run for the dashboard countdown (APScheduler will
            # actually fire it at startup_time + interval).
            sch.next_check_at = now + timedelta(seconds=sch.interval_seconds)
        db.commit()
    finally:
        db.close()

    yield

    worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    scheduler.stop()


app = FastAPI(title="Readex", version="0.1.0", lifespan=lifespan)
app.include_router(series.router)
app.include_router(search.router)
app.include_router(downloads.router)
app.include_router(schedules.router)
app.include_router(settings_router.router)
app.include_router(import_library.router)
app.include_router(proxy.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


import os
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Serve React frontend in production. Mount /assets/ for hashed bundles, then a
# catch-all that returns index.html for any other path so React Router can
# handle deep links like /search, /library, /series/123 on hard refresh.
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_path = os.path.join(frontend_dist, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Try to serve static file from the dist root first (favicon, robots, etc.)
        candidate = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        # Otherwise fall back to index.html so React Router takes over
        return FileResponse(index_path)
