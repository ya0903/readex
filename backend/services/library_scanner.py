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
            root = self._root_for(series)
            folder = os.path.join(root, series.folder_name)
            if not os.path.isdir(folder):
                continue

            on_disk = dict(_existing_paths(folder))  # {chapter_number: path}
            if not on_disk:
                continue

            chapters = db.query(Chapter).filter_by(series_id=series.id).all()
            for ch in chapters:
                path = on_disk.get(ch.chapter_number)
                if path and ch.status != "downloaded":
                    ch.status = "downloaded"
                    ch.file_path = path
        db.commit()
