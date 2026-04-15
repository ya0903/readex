import asyncio
import logging
from datetime import datetime

from models import Chapter, DownloadQueue, Series
from services.download_service import DownloadService
from sources.registry import SourceRegistry

logger = logging.getLogger("readex.worker")


class DownloadWorker:
    def __init__(self, db_factory, registry: SourceRegistry,
                 download_service: DownloadService, max_concurrent: int = 3):
        self._db_factory = db_factory
        self._registry = registry
        self._download_service = download_service
        self._max_concurrent = max_concurrent
        self._running = False
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self):
        self._running = True
        logger.info("Download worker started")
        while self._running:
            try:
                await self._process_queue()
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(5)

    def stop(self):
        self._running = False

    async def _process_queue(self):
        db = self._db_factory()
        try:
            pending = (
                db.query(DownloadQueue)
                .filter_by(status="pending")
                .order_by(DownloadQueue.priority, DownloadQueue.created_at)
                .limit(self._max_concurrent)
                .all()
            )
            if not pending:
                return

            tasks = [self._download_one(entry.id) for entry in pending]
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            db.close()

    async def _download_one(self, queue_id: int):
        async with self._semaphore:
            db = self._db_factory()
            try:
                entry = db.get(DownloadQueue, queue_id)
                if not entry or entry.status != "pending":
                    return

                entry.status = "active"
                chapter = db.get(Chapter, entry.chapter_id)
                chapter.status = "downloading"
                db.commit()

                series = db.get(Series, chapter.series_id)
                source = self._registry.get(series.source_name)
                if not source:
                    entry.status = "failed"
                    entry.error_message = f"Source '{series.source_name}' not found"
                    chapter.status = "failed"
                    db.commit()
                    return

                from sources.base import ChapterInfo
                ch_info = ChapterInfo(
                    source_chapter_id=chapter.source_chapter_id,
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    url=chapter.source_chapter_url or "",
                )

                # Build a per-chapter ComicInfo.xml so Komga shows series + chapter
                from services.komga_metadata import make_comicinfo_xml
                comicinfo = make_comicinfo_xml(
                    series_title=series.title,
                    chapter_number=chapter.chapter_number,
                    chapter_title=chapter.title,
                )

                # Progress callback writes to the queue entry's progress fields
                # in a short-lived session so the UI sees live updates.
                queue_id = entry.id
                db_factory = self._db_factory

                def _progress(current: int, total: int) -> None:
                    s = db_factory()
                    try:
                        e = s.get(DownloadQueue, queue_id)
                        if e:
                            e.progress_current = current
                            e.progress_total = total
                            s.commit()
                    finally:
                        s.close()

                from config import settings as _settings
                result_path = await self._download_service.download_and_package(
                    source=source,
                    folder_name=series.folder_name,
                    chapter=ch_info,
                    content_type=series.content_type,
                    comicinfo_xml=comicinfo,
                    progress_cb=_progress,
                    library_path=_settings.library_path_for(series.content_type),
                )

                if result_path:
                    chapter.status = "downloaded"
                    chapter.file_path = result_path
                    chapter.downloaded_at = datetime.utcnow()
                    entry.status = "complete"
                else:
                    chapter.status = "downloaded"
                    entry.status = "complete"

                series.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"Downloaded: {series.title} - Ch.{chapter.chapter_number}")

            except Exception as e:
                logger.error(f"Download failed for queue {queue_id}: {e}")
                try:
                    entry = db.get(DownloadQueue, queue_id)
                    if entry:
                        chapter = db.get(Chapter, entry.chapter_id)
                        entry.retries += 1
                        if entry.retries >= 3:
                            entry.status = "failed"
                            entry.error_message = str(e)
                            if chapter:
                                chapter.status = "failed"
                        else:
                            entry.status = "pending"
                            if chapter:
                                chapter.status = "queued"
                        db.commit()
                except Exception:
                    pass
            finally:
                db.close()
