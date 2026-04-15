"""Import existing manga folders (e.g. from Kaizoku or any folder layout) into Readex."""
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Series, Chapter

router = APIRouter(prefix="/api/import", tags=["import"])

CHAPTER_PATTERNS = [
    re.compile(r"chapter\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\bch\.?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\bc(\d+(?:\.\d+)?)\b", re.IGNORECASE),
    re.compile(r"\bv\d+\s+(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\[(\d+)\]"),
    re.compile(r"^(\d+(?:\.\d+)?)\s"),
    re.compile(r"\b(\d+)\b"),  # last resort
]


def _detect_chapter_number(filename: str, fallback: int) -> float:
    """Best-effort: pull a chapter number from a filename."""
    name = os.path.splitext(filename)[0]
    for pat in CHAPTER_PATTERNS:
        m = pat.search(name)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, IndexError):
                continue
    return float(fallback)


def _scan_folder_for_chapters(folder_path: str) -> list[tuple[float, str, str]]:
    """Return list of (chapter_number, filename, full_path) for cbz/cbr/zip files."""
    out: list[tuple[float, str, str]] = []
    try:
        entries = sorted(os.listdir(folder_path))
    except OSError:
        return out
    for i, entry in enumerate(entries):
        full = os.path.join(folder_path, entry)
        if not os.path.isfile(full):
            continue
        ext = entry.lower().rsplit(".", 1)[-1] if "." in entry else ""
        if ext not in ("cbz", "cbr", "zip"):
            continue
        size = 0
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        if size < 100:
            continue
        num = _detect_chapter_number(entry, i + 1)
        out.append((num, entry, full))
    out.sort(key=lambda t: t[0])
    return out


def _all_library_paths() -> list[tuple[str, str | None]]:
    """Return a list of (path, content_type) tuples for every configured library root.

    `content_type` is None for the default `library_path` (since it could
    contain anything).
    """
    seen: set[str] = set()
    out: list[tuple[str, str | None]] = []
    for ct, path in (
        ("manga", settings.manga_path),
        ("manhwa", settings.manhwa_path),
        ("comic", settings.comic_path),
    ):
        if path and path not in seen:
            out.append((path, ct))
            seen.add(path)
    if settings.library_path and settings.library_path not in seen:
        out.append((settings.library_path, None))
    return out


class ScanResult(BaseModel):
    folder: str
    chapter_count: int
    total_size: int  # bytes
    already_imported: bool
    library_root: str  # absolute path to the library this folder belongs to
    suggested_content_type: str  # manga / manhwa / comic / unknown


@router.get("/scan", response_model=list[ScanResult])
def scan_library(db: Session = Depends(get_db)):
    """List folders across all configured library paths.

    Marks ones already in the DB so the UI can show them differently.
    """
    paths = _all_library_paths()
    if not paths:
        raise HTTPException(status_code=500, detail="No library path configured")

    existing_folders = {s.folder_name for s in db.query(Series).all()}
    results: list[ScanResult] = []
    seen_folders: set[str] = set()
    for root, ct in paths:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            if entry in seen_folders:
                continue
            full = os.path.join(root, entry)
            if not os.path.isdir(full):
                continue
            chapters = _scan_folder_for_chapters(full)
            if not chapters:
                continue
            seen_folders.add(entry)
            total_size = sum(os.path.getsize(p) for _, _, p in chapters if os.path.exists(p))
            results.append(
                ScanResult(
                    folder=entry,
                    chapter_count=len(chapters),
                    total_size=total_size,
                    already_imported=entry in existing_folders,
                    library_root=root,
                    suggested_content_type=ct or "unknown",
                )
            )
    return results


class ImportRequest(BaseModel):
    folders: list[str]
    content_type: str = "manga"  # default, user can re-categorise per series after


class ImportResult(BaseModel):
    folder: str
    series_id: int | None
    chapters: int
    error: str | None = None


@router.post("/import", response_model=list[ImportResult])
async def import_folders(
    data: ImportRequest, db: Session = Depends(get_db)
) -> list[ImportResult]:
    """Create Series records for the requested folders and mark their chapters as downloaded.

    After creation, attempt a metadata + cover sync per series so Komga shows
    summaries and cover art on the imported entries.
    """
    # Lazy import to avoid circular dependency at module load time
    from routers.series import _sync_komga_metadata
    from services.kaizoku import remove_by_title as _kaizoku_remove, is_enabled as _kaizoku_on

    paths = _all_library_paths()
    if not paths:
        raise HTTPException(status_code=500, detail="No library path configured")

    existing_folders = {s.folder_name: s for s in db.query(Series).all()}
    results: list[ImportResult] = []
    for folder in data.folders:
        # Find which configured library root contains this folder
        full = None
        for root, _ct in paths:
            candidate = os.path.join(root, folder)
            if os.path.isdir(candidate):
                full = candidate
                break
        if full is None:
            results.append(ImportResult(folder=folder, series_id=None, chapters=0,
                                        error="folder not found"))
            continue
        if folder in existing_folders:
            results.append(ImportResult(
                folder=folder,
                series_id=existing_folders[folder].id,
                chapters=0,
                error="already imported",
            ))
            continue

        chapters = _scan_folder_for_chapters(full)
        if not chapters:
            results.append(ImportResult(folder=folder, series_id=None, chapters=0,
                                        error="no cbz/cbr files found"))
            continue

        # Use folder name as the title and source_id; source_name="imported" marks
        # this as not bound to a scraper yet. The user can later attach one via
        # PATCH /api/series/{id} or the "Match Source" UI.
        # source_id needs to be unique per source — using folder + extra suffix avoids
        # collisions if user re-imports.
        # Clean the display title: underscores → spaces, collapse whitespace.
        # Folder name on disk stays unchanged so existing Komga indexing still works.
        clean_title = re.sub(r"\s+", " ", folder.replace("_", " ")).strip()
        series = Series(
            title=clean_title,
            folder_name=folder,
            source_name="imported",
            source_id=f"local:{folder}",
            content_type=data.content_type,
            status="ongoing",
        )
        db.add(series)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            results.append(ImportResult(folder=folder, series_id=None, chapters=0,
                                        error=f"DB error: {e}"))
            continue
        db.refresh(series)

        added = 0
        for num, filename, full_path in chapters:
            # source_chapter_id has to be unique within this series; use filename
            db.add(Chapter(
                series_id=series.id,
                chapter_number=num,
                title=os.path.splitext(filename)[0],
                source_chapter_id=f"local:{filename}",
                source_chapter_url=None,
                status="downloaded",
                file_path=full_path,
            ))
            added += 1
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            results.append(ImportResult(folder=folder, series_id=series.id,
                                        chapters=0, error=f"chapter insert: {e}"))
            continue

        # Best-effort metadata + cover fetch
        try:
            await _sync_komga_metadata(series, force_cover=True)
        except Exception:
            pass

        # If Kaizoku is configured, remove this series from Kaizoku so it
        # doesn't keep tracking/duplicating downloads. Files are kept on disk.
        if _kaizoku_on():
            try:
                await _kaizoku_remove(series.title)
            except Exception:
                pass

        results.append(ImportResult(folder=folder, series_id=series.id,
                                    chapters=added, error=None))

    return results
