import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base, get_db
from main import app
from models import Series, Chapter, DownloadQueue

@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

def _seed_series_with_chapters(db_session):
    series = Series(
        title="Test", folder_name="Test", source_name="mangadex",
        source_id="x", content_type="manga", status="ongoing",
    )
    db_session.add(series)
    db_session.commit()
    chapters = []
    for i in range(1, 4):
        ch = Chapter(series_id=series.id, chapter_number=float(i),
                     source_chapter_id=f"ch{i}", status="available")
        db_session.add(ch)
        chapters.append(ch)
    db_session.commit()
    return series, chapters

def test_queue_download_specific_chapters(client, db_session):
    series, chapters = _seed_series_with_chapters(db_session)
    resp = client.post("/api/downloads", json={
        "series_id": series.id, "chapter_ids": [chapters[0].id, chapters[1].id],
    })
    assert resp.status_code == 200
    assert resp.json()["queued"] == 2

def test_queue_download_all_available(client, db_session):
    series, chapters = _seed_series_with_chapters(db_session)
    resp = client.post("/api/downloads", json={"series_id": series.id})
    assert resp.status_code == 200
    assert resp.json()["queued"] == 3

def test_get_queue(client, db_session):
    series, chapters = _seed_series_with_chapters(db_session)
    for ch in chapters[:2]:
        ch.status = "queued"
        db_session.add(DownloadQueue(chapter_id=ch.id, priority=0, status="pending", retries=0))
    db_session.commit()
    resp = client.get("/api/downloads/queue")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
