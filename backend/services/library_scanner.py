# readex/backend/services/library_scanner.py
"""On-disk library scanner.

Walks each series's per-content-type library root and marks chapters as
`downloaded` if a matching CBZ already exists on disk. Lets Readex pick up
files that were downloaded outside the app, or by a previous container that
crashed before updating the DB.
"""
import os
import re
from typing import Iterable

from sqlalchemy.orm import Session

from config import settings
from models import Chapter, Series

CHAPTER_FILE_PATTERNS = [
    re.compile(r"^Chapter\s+(\d+(?:\.\d+)?)\.cbz$", re.IGNORECASE),
    re.compile(r"^Issue\s+(\d+(?:\.\d+)?)\.cbz$", re.IGNORECASE),
    re.compile(r"^Ch\.?\s*(\d+(?:\.\d+)?)\.cbz$", re.IGNORECASE),
    re.compile(r"^c(\d+(?:\.\d+)?)\.cbz$", re.IGNORECASE),
]


def _chapter_number_for(filename: str) -> float | None:
    for pat in CHAPTER_FILE_PATTERNS:
        m = pat.match(filename)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def _existing_paths(folder: str) -> Iterable[tuple[float, str]]:
    if not os.path.isdir(folder):
        return
    for entry in os.listdir(folder):
        full = os.path.join(folder, entry)
        if not os.path.isfile(full):
            continue
        num = _chapter_number_for(entry)
        if num is None:
            continue
        yield num, full


class LibraryScanner:
    def __init__(self, library_path: str | None = None):
        # If a library_path is explicitly passed, use it as a fixed root for
        # every series (lets tests override the path). Otherwise resolve
        # per-series via settings.library_path_for().
        self.library_path = library_path

    def _root_for(self, series: Series) -> str:
        if self.library_path is not None:
            return self.library_path
        return settings.library_path_for(series.content_type)

    def scan(self, db: Session) -> None:
        all_series = db.query(Series).all()
        for series in all_series:
            self.scan_series(db, series)
        db.commit()

    def scan_series(self, db: Session, series: Series) -> dict:
        """Scan a single series's folder and reconcile chapter status with what's
        on disk.

        Returns counts: {scanned, updated, missing}.
          - scanned: matching CBZ files found in the folder
          - updated: chapters whose status was flipped to "downloaded"
          - missing: chapters previously marked downloaded whose file is gone
                     (those get flipped back to "available")
        Caller is responsible for db.commit() if running in a transaction.
        """
        root = self._root_for(series)
        folder = os.path.join(root, series.folder_name)
        on_disk = dict(_existing_paths(folder)) if os.path.isdir(folder) else {}

        chapters = db.query(Chapter).filter_by(series_id=series.id).all()
        updated = 0
        missing = 0
        for ch in chapters:
            path = on_disk.get(ch.chapter_number)
            if path:
                if ch.status != "downloaded" or ch.file_path != path:
                    ch.status = "downloaded"
                    ch.file_path = path
                    updated += 1
            else:
                # File is gone but DB still says downloaded — drop back to
                # available so the user knows it can be re-fetched.
                if ch.status == "downloaded":
                    ch.status = "available"
                    ch.file_path = None
                    missing += 1
        return {"scanned": len(on_disk), "updated": updated, "missing": missing}
