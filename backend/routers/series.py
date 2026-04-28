import os
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Series, Chapter, DownloadQueue
from schemas import (
    SeriesCreate,
    SeriesUpdate,
    SeriesOut,
    SeriesDetailOut,
    ChapterOut,
)
from services.komga_metadata import write_series_json, download_cover
from services.komga import trigger_scan_in_background as _komga_scan
from services.metadata_service import MetadataService

router = APIRouter(prefix="/api/series", tags=["series"])


def _merge_chapters(db: Session, series: Series, source_chapters) -> int:
    """Insert new chapters from source into DB, skipping duplicates.

    If a chapter with the same `chapter_number` already exists in the series
    but with a different `source_chapter_id` (e.g. it was imported with a
    `local:` id), rebind the existing chapter to the new source id instead of
    inserting a duplicate. This keeps imported series clean after match-source
    + refresh cycles.

    Returns count of newly added chapters (excludes rebinds).
    """
    existing = db.query(Chapter).filter_by(series_id=series.id).all()
    existing_by_id = {ch.source_chapter_id: ch for ch in existing}
    existing_by_num = {ch.chapter_number: ch for ch in existing}

    added_ids: set[str] = set()
    added_nums: set[float] = set()
    added = 0

    for ch_info in source_chapters:
        if ch_info.source_chapter_id in existing_by_id:
            continue
        if ch_info.source_chapter_id in added_ids:
            continue

        # Rebind existing chapter at this number → keep file_path/status
        existing_at_num = existing_by_num.get(ch_info.chapter_number)
        if existing_at_num is not None and ch_info.chapter_number not in added_nums:
            existing_at_num.source_chapter_id = ch_info.source_chapter_id
            existing_at_num.source_chapter_url = ch_info.url or None
            if not existing_at_num.title and ch_info.title:
                existing_at_num.title = ch_info.title
            existing_by_id[ch_info.source_chapter_id] = existing_at_num
            added_nums.add(ch_info.chapter_number)
            continue

        added_ids.add(ch_info.source_chapter_id)
        added_nums.add(ch_info.chapter_number)
        db.add(
            Chapter(
                series_id=series.id,
                chapter_number=ch_info.chapter_number,
                title=ch_info.title,
                source_chapter_id=ch_info.source_chapter_id,
                source_chapter_url=ch_info.url or None,
                status="available",
            )
        )
        added += 1
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return added


async def _sync_komga_metadata(series: Series, force_cover: bool = False) -> str | None:
    """Fetch metadata via the configured URL/title and write series.json + cover.

    Returns the path written, or None if no metadata was available.
    """
    folder = os.path.join(settings.library_path_for(series.content_type), series.folder_name)
    svc = MetadataService()
    meta = None
    if series.metadata_url:
        try:
            meta = await svc.fetch_from_url(series.metadata_url)
        except Exception:
            meta = None
    if meta is None and settings.metadata_auto_lookup:
        try:
            meta = await svc.lookup_any(series.title)
        except Exception:
            meta = None
    json_path: str | None = None
    if meta is not None:
        try:
            json_path = write_series_json(folder, meta)
        except Exception:
            json_path = None

        # Also update the Readex DB row so the UI / library filter reflects
        # what the metadata source says (ongoing / complete / etc).
        try:
            from sqlalchemy.orm import object_session
            ses = object_session(series)
            if ses is not None and meta.status and meta.status != series.status:
                series.status = meta.status
                if not series.cover_url and meta.cover_url:
                    series.cover_url = meta.cover_url
                ses.commit()
        except Exception:
            pass

    # Pick the best available cover URL: metadata first, then series.cover_url
    # (set from the source's search result), then nothing.
    cover_url = None
    if meta and meta.cover_url:
        cover_url = meta.cover_url
    elif series.cover_url:
        cover_url = series.cover_url
    if cover_url:
        try:
            await download_cover(folder, cover_url, force=force_cover)
        except Exception:
            pass

    final_path = json_path or (folder if cover_url else None)
    # Best-effort: ask Komga to re-scan so the new metadata shows up
    if final_path:
        try:
            _komga_scan(folder)
        except Exception:
            pass
    # Record the sync so bulk "Sync All" can skip unchanged series later. We
    # only mark as synced when we actually wrote a series.json, not when we
    # only refreshed a cover — the cover alone isn't what Komga surfaces.
    if json_path is not None:
        try:
            from sqlalchemy.orm import object_session
            ses = object_session(series)
            if ses is not None:
                series.metadata_synced_at = datetime.utcnow()
                series.metadata_synced_url = series.metadata_url
                ses.commit()
        except Exception:
            pass
    return final_path


@router.get("", response_model=list[SeriesOut])
def list_series(db: Session = Depends(get_db)):
    series_list = db.query(Series).order_by(Series.updated_at.desc()).all()
    results = []
    for s in series_list:
        total = db.query(Chapter).filter_by(series_id=s.id).count()
        downloaded = (
            db.query(Chapter).filter_by(series_id=s.id, status="downloaded").count()
        )
        out = SeriesOut.model_validate(s)
        out.chapter_count = total
        out.downloaded_count = downloaded
        results.append(out)
    return results


@router.post("", response_model=SeriesOut, status_code=201)
async def create_series(
    data: SeriesCreate,
    request: Request,
    replace: bool = False,
    delete_files: bool = False,
    db: Session = Depends(get_db),
):
    """Create a series. Pass ?replace=true to overwrite an existing one with the
    same (source_name, source_id). Pass &delete_files=true to also remove the
    old folder on disk."""
    existing = (
        db.query(Series)
        .filter_by(source_name=data.source_name, source_id=data.source_id)
        .first()
    )
    if existing:
        if not replace:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        f'"{existing.title}" is already in your library. '
                        "Use Replace to overwrite, or open it from the Library page."
                    ),
                    "existing_series_id": existing.id,
                    "existing_title": existing.title,
                    "existing_folder": existing.folder_name,
                },
            )
        # Replace: delete existing series and (optionally) its folder, then continue
        old_folder = os.path.join(settings.library_path_for(existing.content_type), existing.folder_name)
        db.delete(existing)
        db.commit()
        if delete_files and os.path.isdir(old_folder):
            try:
                shutil.rmtree(old_folder)
            except Exception as e:
                import logging
                logging.getLogger("readex").warning(
                    f"Failed to delete old folder {old_folder}: {e}"
                )

    series = Series(
        title=data.title,
        folder_name=data.folder_name,
        source_name=data.source_name,
        source_id=data.source_id,
        content_type=data.content_type,
        status=data.status,
        metadata_url=data.metadata_url,
        cover_url=data.cover_url,
    )
    db.add(series)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Could not create series: {e}")
    db.refresh(series)

    # Auto-fetch chapter list from source on creation (skip for "imported" sources)
    registry = getattr(request.app.state, "source_registry", None)
    if registry is not None:
        source = registry.get(data.source_name)
        if source is not None:
            try:
                ch_list = await source.get_chapters(data.source_id)
                _merge_chapters(db, series, ch_list)
            except Exception:
                pass

    # Write Komga series.json so summaries/genres show up in Komga (best-effort)
    try:
        await _sync_komga_metadata(series)
    except Exception:
        import logging
        logging.getLogger("readex").warning(
            "metadata sync failed during series creation", exc_info=True
        )

    total = db.query(Chapter).filter_by(series_id=series.id).count()
    out = SeriesOut.model_validate(series)
    out.chapter_count = total
    return out


@router.get("/{series_id}", response_model=SeriesDetailOut)
def get_series(series_id: int, db: Session = Depends(get_db)):
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    out = SeriesDetailOut.model_validate(series)
    chapters_sorted = sorted(series.chapters, key=lambda c: c.chapter_number)
    out.chapters = [ChapterOut.model_validate(ch) for ch in chapters_sorted]
    out.chapter_count = len(series.chapters)
    out.downloaded_count = sum(
        1 for ch in series.chapters if ch.status == "downloaded"
    )
    return out


@router.post("/{series_id}/refresh")
async def refresh_chapters(
    series_id: int, request: Request, db: Session = Depends(get_db)
):
    """Fetch latest chapter list from source and merge into DB."""
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    registry = getattr(request.app.state, "source_registry", None)
    if registry is None:
        raise HTTPException(status_code=500, detail="Source registry not available")
    source = registry.get(series.source_name)
    if source is None:
        raise HTTPException(
            status_code=400,
            detail=f"Source '{series.source_name}' is not registered",
        )

    try:
        ch_list = await source.get_chapters(series.source_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Source error: {e}")

    added = _merge_chapters(db, series, ch_list)

    # Prune chapters that no longer exist on the source AND haven't been
    # downloaded yet. (Don't touch downloaded chapters — those files exist on disk.)
    source_ids = {ch.source_chapter_id for ch in ch_list}
    stale = db.query(Chapter).filter(
        Chapter.series_id == series.id,
        Chapter.source_chapter_id.notin_(source_ids),
        Chapter.status != "downloaded",
    ).all()
    removed = len(stale)
    for ch in stale:
        # Remove pending queue entries first so FK doesn't block
        db.query(DownloadQueue).filter_by(chapter_id=ch.id).delete()
        db.delete(ch)
    if removed:
        db.commit()

    total = db.query(Chapter).filter_by(series_id=series.id).count()
    return {"added": added, "removed": removed, "total": total}


@router.post("/{series_id}/scan-files")
def scan_series_files(series_id: int, db: Session = Depends(get_db)):
    """Reconcile chapter status with files on disk for a single series.

    Marks chapters as "downloaded" when a matching CBZ exists, and flips
    chapters back to "available" when their previously-recorded file is gone.
    Useful after manual file moves, drive remounts, or partial deletions.
    """
    from services.library_scanner import LibraryScanner

    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    scanner = LibraryScanner()
    counts = scanner.scan_series(db, series)
    db.commit()
    return counts


@router.post("/{series_id}/match-source")
async def match_source(
    series_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    """Bind an existing series to a scraper source so it can be updated.

    payload: { "source_name": "...", "source_id": "..." }
    Marks chapters whose `chapter_number` already exist as `downloaded` (preserved).
    Adds new chapters from the source.
    """
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    src_name = payload.get("source_name")
    src_id = payload.get("source_id")
    if not src_name or not src_id:
        raise HTTPException(
            status_code=400, detail="source_name and source_id are required"
        )

    registry = getattr(request.app.state, "source_registry", None)
    if registry is None or registry.get(src_name) is None:
        raise HTTPException(status_code=400, detail=f"Source '{src_name}' is not registered")

    series.source_name = src_name
    series.source_id = src_id
    db.commit()

    source = registry.get(src_name)
    try:
        ch_list = await source.get_chapters(src_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Source error: {e}")

    # Use the shared merge helper which:
    #   - dedupes by source_chapter_id (avoids unique constraint violations
    #     when a scraper returns the same chapter id twice)
    #   - rebinds existing chapters at the same chapter_number (preserves
    #     downloaded files, just rewrites the source_chapter_id)
    before = db.query(Chapter).filter_by(series_id=series.id).count()
    added = _merge_chapters(db, series, ch_list)
    after = db.query(Chapter).filter_by(series_id=series.id).count()
    linked = max(0, before - (after - added))

    # Clear pending/failed queue entries for chapters that still have a non-numeric
    # `source_chapter_id` from the previous source (won't work with the new one).
    # The chapter rows stay; the user can re-queue them after the source switch.
    new_source_ids = {ch.source_chapter_id for ch in ch_list}
    stale_q = (
        db.query(DownloadQueue)
        .join(Chapter, Chapter.id == DownloadQueue.chapter_id)
        .filter(
            Chapter.series_id == series.id,
            DownloadQueue.status.in_(["pending", "failed", "active"]),
            ~Chapter.source_chapter_id.in_(list(new_source_ids)),
        )
        .all()
    )
    cleared = 0
    for e in stale_q:
        ch = db.get(Chapter, e.chapter_id)
        if ch and ch.status in ("queued", "downloading", "failed"):
            ch.status = "available"
        db.delete(e)
        cleared += 1

    try:
        await _sync_komga_metadata(series, force_cover=True)
    except Exception:
        pass

    db.commit()
    return {
        "linked": linked, "added": added,
        "source_name": src_name, "source_id": src_id,
        "queue_cleared": cleared,
    }


# In-memory state for the bulk metadata sync. Survives client navigation but
# resets on container restart (run again to re-sync after restart).
_sync_state: dict = {
    "status": "idle",  # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "processed": 0,
    "updated": 0,
    "skipped": 0,
    "failed": 0,
    "failed_list": [],
    "current": None,
}


async def _bulk_sync_runner(force: bool = False):
    """Background task: sync metadata + cover for series that need it.

    Skips series that have already been synced with their current metadata_url
    (as recorded by `metadata_synced_at`). Set `force=True` to bypass skip
    logic and re-sync every series — useful after a Komga rebuild.
    """
    from database import SessionLocal
    s = SessionLocal()
    try:
        series_list = s.query(Series).all()
        _sync_state.update({
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "finished_at": None,
            "total": len(series_list),
            "processed": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "failed_list": [],
            "current": None,
        })
        for series in series_list:
            _sync_state["current"] = series.title
            # Skip: already synced with the current metadata_url (or with
            # auto-lookup, where both stored and current URL are null).
            if (not force
                    and series.metadata_synced_at is not None
                    and series.metadata_synced_url == series.metadata_url):
                _sync_state["skipped"] += 1
                _sync_state["processed"] += 1
                continue
            try:
                result = await _sync_komga_metadata(series, force_cover=True)
                if result:
                    _sync_state["updated"] += 1
                else:
                    _sync_state["failed"] += 1
                    _sync_state["failed_list"].append({
                        "id": series.id, "title": series.title, "reason": "no metadata match"
                    })
            except Exception as e:
                _sync_state["failed"] += 1
                _sync_state["failed_list"].append({
                    "id": series.id, "title": series.title, "reason": f"error: {e}"
                })
            _sync_state["processed"] += 1
        _sync_state["status"] = "done"
        _sync_state["finished_at"] = datetime.utcnow().isoformat()
        _sync_state["current"] = None
    except Exception as e:
        _sync_state["status"] = "error"
        _sync_state["current"] = str(e)
    finally:
        s.close()


@router.post("/metadata/sync-all")
async def start_sync_all_metadata(force: bool = False):
    """Start a background metadata sync.

    By default, only processes series that haven't been synced with their
    current `metadata_url` yet — a repeat click won't re-sync anything that's
    already up to date. Pass `?force=true` to re-sync every series anyway
    (e.g. after Komga loses its metadata and needs everything re-written).

    Returns immediately. Poll GET /api/series/metadata/sync-all/status for
    progress + results.
    """
    import asyncio
    if _sync_state["status"] == "running":
        return {"status": "running", "message": "A sync is already in progress."}
    asyncio.create_task(_bulk_sync_runner(force=force))
    return {"status": "started", "force": force}


@router.get("/metadata/sync-all/status")
def sync_all_metadata_status():
    """Return current/last bulk sync state."""
    return _sync_state


@router.post("/{series_id}/metadata/sync")
async def sync_metadata(series_id: int, db: Session = Depends(get_db)):
    """(Re)write Komga series.json + cover for one series and trigger Komga rescan."""
    import os
    from services.komga import is_enabled as komga_enabled, trigger_scan_for_path

    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    path = await _sync_komga_metadata(series, force_cover=True)
    if path is None:
        msg = (
            f"Could not fetch metadata for '{series.title}'. "
            + (
                "The metadata URL you set didn't resolve — the metadata source might be temporarily down (Jikan/MAL has frequent 5xx) or the URL is wrong."
                if series.metadata_url
                else "No matching series found via auto-lookup. Set a metadata URL on this series."
            )
        )
        raise HTTPException(status_code=502, detail=msg)

    folder = os.path.join(settings.library_path_for(series.content_type), series.folder_name)
    cover_files = [
        f for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f)) and f.startswith("cover.")
    ] if os.path.isdir(folder) else []
    has_series_json = os.path.isfile(os.path.join(folder, "series.json"))

    # Trigger Komga rescan synchronously so we can report whether it actually fired
    komga_scanned = False
    if komga_enabled():
        try:
            komga_scanned = await trigger_scan_for_path(folder)
        except Exception:
            pass

    return {
        "written": path,
        "wrote_series_json": has_series_json,
        "cover_file": cover_files[0] if cover_files else None,
        "komga_enabled": komga_enabled(),
        "komga_rescan_triggered": komga_scanned,
    }


@router.patch("/{series_id}", response_model=SeriesOut)
async def update_series(
    series_id: int, data: SeriesUpdate, db: Session = Depends(get_db)
):
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    fields = data.model_dump(exclude_unset=True)
    metadata_changed = "metadata_url" in fields
    new_folder = fields.get("folder_name")
    old_folder_name = series.folder_name

    # Validate new folder doesn't collide with another series
    if new_folder and new_folder != old_folder_name:
        clash = (
            db.query(Series)
            .filter(Series.folder_name == new_folder, Series.id != series.id)
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"Another series already uses the folder '{new_folder}'",
            )

    for field, value in fields.items():
        setattr(series, field, value)
    # If the user changed the metadata URL, invalidate the sync marker so the
    # next "Sync All" picks this series up instead of skipping it.
    if metadata_changed:
        series.metadata_synced_at = None
        series.metadata_synced_url = None
    db.commit()
    db.refresh(series)

    # Rename the folder on disk + update chapter file paths
    if new_folder and new_folder != old_folder_name:
        lib = settings.library_path_for(series.content_type)
        old_path = os.path.join(lib, old_folder_name)
        new_path = os.path.join(lib, new_folder)
        if os.path.isdir(old_path):
            try:
                os.rename(old_path, new_path)
                # Rewrite chapter file_path entries that pointed inside the old folder
                old_prefix = old_path + os.sep
                new_prefix = new_path + os.sep
                for ch in db.query(Chapter).filter_by(series_id=series.id).all():
                    if ch.file_path and ch.file_path.startswith(old_prefix):
                        ch.file_path = new_prefix + ch.file_path[len(old_prefix):]
                db.commit()
            except OSError as e:
                import logging
                logging.getLogger("readex").warning(
                    f"Failed to rename folder {old_path} -> {new_path}: {e}"
                )

    if metadata_changed:
        try:
            await _sync_komga_metadata(series, force_cover=True)
        except Exception:
            pass

    return SeriesOut.model_validate(series)


@router.post("/{series_id}/dedupe")
def dedupe_chapters(series_id: int, db: Session = Depends(get_db)):
    """Collapse duplicate chapters (same chapter_number) into a single entry.

    Keeps the chapter that has a downloaded file_path; otherwise keeps any one.
    Removes pending queue entries for the duplicates first.
    """
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    chapters = db.query(Chapter).filter_by(series_id=series.id).order_by(
        Chapter.chapter_number, Chapter.id
    ).all()

    by_num: dict[float, list[Chapter]] = {}
    for ch in chapters:
        by_num.setdefault(ch.chapter_number, []).append(ch)

    removed = 0
    for num, group in by_num.items():
        if len(group) <= 1:
            continue
        # Prefer the one with file_path / downloaded status
        keeper = next((c for c in group if c.status == "downloaded" and c.file_path), None)
        if keeper is None:
            keeper = group[0]
        for ch in group:
            if ch.id == keeper.id:
                continue
            db.query(DownloadQueue).filter_by(chapter_id=ch.id).delete()
            db.delete(ch)
            removed += 1
    if removed:
        db.commit()
    total = db.query(Chapter).filter_by(series_id=series.id).count()
    return {"removed": removed, "total": total}


@router.post("/{series_id}/chapters/delete")
def delete_chapters(
    series_id: int, payload: dict, db: Session = Depends(get_db)
):
    """Bulk-delete chapters. Payload: { "chapter_ids": [int], "delete_files": bool }

    - Removes DB rows and any pending queue entries.
    - If `delete_files` is true, also deletes the CBZ file on disk.
    """
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    chapter_ids = payload.get("chapter_ids") or []
    delete_files = bool(payload.get("delete_files"))
    if not isinstance(chapter_ids, list) or not chapter_ids:
        raise HTTPException(status_code=400, detail="chapter_ids must be a non-empty list")

    chapters = db.query(Chapter).filter(
        Chapter.series_id == series.id,
        Chapter.id.in_(chapter_ids),
    ).all()

    removed = 0
    files_removed = 0
    for ch in chapters:
        if delete_files and ch.file_path and os.path.isfile(ch.file_path):
            try:
                os.remove(ch.file_path)
                files_removed += 1
            except OSError:
                pass
        db.query(DownloadQueue).filter_by(chapter_id=ch.id).delete()
        db.delete(ch)
        removed += 1
    if removed:
        db.commit()
    return {"removed": removed, "files_removed": files_removed}


@router.get("/{series_id}/cover")
async def get_series_cover(series_id: int, db: Session = Depends(get_db)):
    """Return the series cover image.

    Lookup order:
      1. cover.{jpg|png|webp|jpeg} in the series folder on disk
      2. fetch series.cover_url through the image proxy and stream the result
      3. 404
    """
    from fastapi.responses import FileResponse, Response
    from services.komga_metadata import COVER_FILENAMES

    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    folder = os.path.join(settings.library_path_for(series.content_type), series.folder_name)
    for name in COVER_FILENAMES:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            mime = (
                "image/png" if name.endswith(".png")
                else "image/webp" if name.endswith(".webp")
                else "image/jpeg"
            )
            return FileResponse(path, media_type=mime, headers={
                "Cache-Control": "public, max-age=300",
            })

    # Fall back to the source's cover URL (proxied to handle Referer)
    if series.cover_url:
        import httpx
        from urllib.parse import urlparse
        UA = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        host = urlparse(series.cover_url).hostname or ""
        referer = f"https://{host}/" if host else ""
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as c:
                r = await c.get(series.cover_url, headers={
                    "User-Agent": UA, "Referer": referer,
                    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
                })
                if r.status_code < 400 and r.content:
                    return Response(
                        content=r.content,
                        media_type=r.headers.get("content-type", "image/jpeg").split(";")[0].strip(),
                        headers={"Cache-Control": "public, max-age=300"},
                    )
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="No cover available")


@router.delete("/{series_id}", status_code=204)
def delete_series(
    series_id: int, delete_files: bool = False, db: Session = Depends(get_db)
):
    """Delete a series. If ?delete_files=true, also remove its folder on disk."""
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    folder = os.path.join(settings.library_path_for(series.content_type), series.folder_name)
    db.delete(series)
    db.commit()
    if delete_files and os.path.isdir(folder):
        try:
            shutil.rmtree(folder)
        except Exception as e:
            # Don't 500 the request — DB delete already succeeded
            import logging
            logging.getLogger("readex").warning(
                f"Failed to delete folder {folder}: {e}"
            )
