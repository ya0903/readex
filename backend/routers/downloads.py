from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Series, Chapter, DownloadQueue
from schemas import DownloadRequest, QueueItemOut

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("")
def queue_download(data: DownloadRequest, db: Session = Depends(get_db)):
    series = db.get(Series, data.series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if data.chapter_ids:
        chapters = db.query(Chapter).filter(
            Chapter.id.in_(data.chapter_ids),
            Chapter.series_id == series.id,
            Chapter.status == "available",
        ).all()
    else:
        chapters = db.query(Chapter).filter_by(
            series_id=series.id, status="available",
        ).all()
    queued = 0
    for ch in chapters:
        ch.status = "queued"
        # Remove any stale queue entry for this chapter first (e.g. from a
        # failed prior attempt) so the unique constraint doesn't explode.
        db.query(DownloadQueue).filter_by(chapter_id=ch.id).delete()
        db.flush()
        db.add(DownloadQueue(chapter_id=ch.id, priority=0, status="pending", retries=0))
        queued += 1
    db.commit()
    return {"queued": queued}


@router.get("/queue", response_model=list[QueueItemOut])
def get_queue(db: Session = Depends(get_db)):
    entries = db.query(DownloadQueue).filter(
        DownloadQueue.status.in_(["pending", "active"])
    ).order_by(DownloadQueue.priority, DownloadQueue.created_at).all()
    results = []
    for entry in entries:
        chapter = db.get(Chapter, entry.chapter_id)
        series = db.get(Series, chapter.series_id)
        results.append(QueueItemOut(
            id=entry.id, chapter_id=entry.chapter_id,
            series_title=series.title, chapter_number=chapter.chapter_number,
            priority=entry.priority, status=entry.status,
            error_message=entry.error_message, retries=entry.retries,
            progress_current=entry.progress_current,
            progress_total=entry.progress_total,
            created_at=entry.created_at,
        ))
    return results


@router.post("/series-retry-failed")
def retry_failed_for_series(payload: dict, db: Session = Depends(get_db)):
    """Retry every failed download for the given series IDs.

    Payload: { "series_ids": [int] }
    """
    ids = payload.get("series_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="series_ids required")
    # Find all failed queue entries that belong to chapters of these series
    entries = (
        db.query(DownloadQueue)
        .join(Chapter, Chapter.id == DownloadQueue.chapter_id)
        .filter(Chapter.series_id.in_(ids), DownloadQueue.status == "failed")
        .all()
    )
    retried = 0
    for e in entries:
        e.status = "pending"
        e.error_message = None
        e.retries = 0
        e.progress_current = 0
        e.progress_total = 0
        ch = db.get(Chapter, e.chapter_id)
        if ch:
            ch.status = "queued"
        retried += 1
    if retried:
        db.commit()
    return {"retried": retried}


@router.post("/queue/retry")
def retry_queue_items(payload: dict, db: Session = Depends(get_db)):
    """Retry queue items by id. Resets status, clears retries/error, marks chapter queued.

    Payload: {"queue_ids": [int], "all_failed": bool}
    If `all_failed=true`, retries every failed item regardless of `queue_ids`.
    """
    ids = payload.get("queue_ids") or []
    all_failed = bool(payload.get("all_failed"))
    q = db.query(DownloadQueue).filter_by(status="failed") if all_failed else (
        db.query(DownloadQueue).filter(DownloadQueue.id.in_(ids))
        if ids else None
    )
    if q is None:
        raise HTTPException(status_code=400, detail="queue_ids or all_failed required")

    entries = q.all()
    retried = 0
    for e in entries:
        e.status = "pending"
        e.error_message = None
        e.retries = 0
        e.progress_current = 0
        e.progress_total = 0
        ch = db.get(Chapter, e.chapter_id)
        if ch:
            ch.status = "queued"
        retried += 1
    if retried:
        db.commit()
    return {"retried": retried}


@router.post("/queue/delete")
def delete_queue_items(payload: dict, db: Session = Depends(get_db)):
    """Delete queue entries by id, OR all items matching a status filter.

    Payload: {"queue_ids": [int], "status": "failed"|"pending"|...}
    Resets the linked chapter back to "available" so it can be re-queued.
    """
    ids = payload.get("queue_ids") or []
    status_filter = payload.get("status")
    q = db.query(DownloadQueue)
    if ids:
        q = q.filter(DownloadQueue.id.in_(ids))
    elif status_filter:
        q = q.filter_by(status=status_filter)
    else:
        raise HTTPException(status_code=400, detail="queue_ids or status required")

    entries = q.all()
    removed = 0
    for e in entries:
        ch = db.get(Chapter, e.chapter_id)
        if ch and ch.status in ("queued", "downloading", "failed"):
            ch.status = "available"
        db.delete(e)
        removed += 1
    if removed:
        db.commit()
    return {"removed": removed}


@router.get("/recent")
def get_recent_downloads(limit: int = 20, db: Session = Depends(get_db)):
    chapters = db.query(Chapter).filter_by(status="downloaded").order_by(
        Chapter.downloaded_at.desc()
    ).limit(limit).all()
    results = []
    for ch in chapters:
        series = db.get(Series, ch.series_id)
        results.append({
            "chapter_id": ch.id, "series_title": series.title,
            "series_id": series.id, "chapter_number": ch.chapter_number,
            "source_name": series.source_name,
            "downloaded_at": ch.downloaded_at.isoformat() if ch.downloaded_at else None,
        })
    return results
