# readex/backend/tests/test_library_scanner.py
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Series, Chapter
from services.library_scanner import LibraryScanner


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def library_dir(tmp_path):
    series_dir = tmp_path / "One Piece"
    series_dir.mkdir()
    (series_dir / "Chapter 1.cbz").write_bytes(b"fake")
    (series_dir / "Chapter 2.cbz").write_bytes(b"fake")
    (series_dir / "Chapter 3.cbz").write_bytes(b"fake")
    return tmp_path


def test_scan_marks_existing_chapters_as_downloaded(db, library_dir):
    series = Series(
        title="One Piece", folder_name="One Piece",
        source_name="mangadex", source_id="op-1",
        content_type="manga", status="ongoing",
    )
    db.add(series)
    db.commit()
    for i in range(1, 6):
        ch = Chapter(
            series_id=series.id, chapter_number=float(i),
            source_chapter_id=f"ch{i}", status="available",
        )
        db.add(ch)
    db.commit()

    scanner = LibraryScanner(library_path=str(library_dir))
    scanner.scan(db)

    chapters = db.query(Chapter).filter_by(series_id=series.id).order_by(Chapter.chapter_number).all()
    assert chapters[0].status == "downloaded"  # Ch 1
    assert chapters[1].status == "downloaded"  # Ch 2
    assert chapters[2].status == "downloaded"  # Ch 3
    assert chapters[3].status == "available"   # Ch 4
    assert chapters[4].status == "available"   # Ch 5


def test_scan_handles_comic_naming(db, tmp_path):
    series_dir = tmp_path / "Batman (2016)"
    series_dir.mkdir()
    (series_dir / "Issue 001.cbz").write_bytes(b"fake")

    series = Series(
        title="Batman (2016)", folder_name="Batman (2016)",
        source_name="getcomics", source_id="bat-1",
        content_type="comic", status="ongoing",
    )
    db.add(series)
    db.commit()
    ch = Chapter(
        series_id=series.id, chapter_number=1.0,
        source_chapter_id="iss1", status="available",
    )
    db.add(ch)
    db.commit()

    scanner = LibraryScanner(library_path=str(tmp_path))
    scanner.scan(db)
    chapter = db.query(Chapter).first()
    assert chapter.status == "downloaded"


def test_scan_ignores_unknown_folders(db, tmp_path):
    unknown_dir = tmp_path / "Unknown Series"
    unknown_dir.mkdir()
    (unknown_dir / "Chapter 1.cbz").write_bytes(b"fake")

    scanner = LibraryScanner(library_path=str(tmp_path))
    scanner.scan(db)
    assert db.query(Series).count() == 0
