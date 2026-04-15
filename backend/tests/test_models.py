from models import Series, Chapter, DownloadQueue, Schedule


def test_create_series(db):
    series = Series(
        title="One Piece",
        folder_name="One Piece",
        source_name="mangadex",
        source_id="abc123",
        content_type="manga",
        status="ongoing",
    )
    db.add(series)
    db.commit()
    db.refresh(series)
    assert series.id is not None
    assert series.title == "One Piece"
    assert series.content_type == "manga"


def test_create_chapter_linked_to_series(db):
    series = Series(
        title="One Piece",
        folder_name="One Piece",
        source_name="mangadex",
        source_id="abc123",
        content_type="manga",
        status="ongoing",
    )
    db.add(series)
    db.commit()

    chapter = Chapter(
        series_id=series.id,
        chapter_number=1100.0,
        title="Chapter 1100",
        source_chapter_id="ch-xyz",
        status="available",
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    assert chapter.series_id == series.id
    assert chapter.chapter_number == 1100.0
    assert chapter.status == "available"


def test_create_download_queue_entry(db):
    series = Series(
        title="Test", folder_name="Test", source_name="mangadex",
        source_id="x", content_type="manga", status="ongoing",
    )
    db.add(series)
    db.commit()

    chapter = Chapter(
        series_id=series.id, chapter_number=1.0,
        source_chapter_id="ch1", status="queued",
    )
    db.add(chapter)
    db.commit()

    entry = DownloadQueue(
        chapter_id=chapter.id, priority=1, status="pending", retries=0,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    assert entry.status == "pending"
    assert entry.retries == 0


def test_create_schedule(db):
    series = Series(
        title="Test", folder_name="Test", source_name="mangadex",
        source_id="x", content_type="manga", status="ongoing",
    )
    db.add(series)
    db.commit()

    schedule = Schedule(
        series_id=series.id, interval_seconds=21600, enabled=True,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    assert schedule.interval_seconds == 21600
    assert schedule.enabled is True
