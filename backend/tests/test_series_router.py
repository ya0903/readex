import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base, get_db
from main import app
from models import Series, Chapter

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

def test_list_series_empty(client):
    resp = client.get("/api/series")
    assert resp.status_code == 200
    assert resp.json() == []

def test_create_series(client):
    resp = client.post("/api/series", json={
        "title": "One Piece", "folder_name": "One Piece",
        "source_name": "mangadex", "source_id": "abc123",
        "content_type": "manga", "status": "ongoing",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "One Piece"
    assert data["id"] is not None

def test_get_series_detail(client, db_session):
    series = Series(
        title="Test", folder_name="Test", source_name="mangadex",
        source_id="x", content_type="manga", status="ongoing",
    )
    db_session.add(series)
    db_session.commit()
    ch = Chapter(series_id=series.id, chapter_number=1.0, source_chapter_id="ch1", status="downloaded")
    db_session.add(ch)
    db_session.commit()
    resp = client.get(f"/api/series/{series.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test"
    assert len(data["chapters"]) == 1

def test_delete_series(client, db_session):
    series = Series(
        title="ToDelete", folder_name="ToDelete", source_name="mangadex",
        source_id="x", content_type="manga", status="ongoing",
    )
    db_session.add(series)
    db_session.commit()
    resp = client.delete(f"/api/series/{series.id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/series/{series.id}")
    assert resp.status_code == 404

def test_update_series(client, db_session):
    series = Series(
        title="Old", folder_name="Old", source_name="mangadex",
        source_id="x", content_type="manga", status="ongoing",
    )
    db_session.add(series)
    db_session.commit()
    resp = client.patch(f"/api/series/{series.id}", json={
        "title": "New Title", "metadata_url": "https://anilist.co/manga/12345",
    })
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"
    assert resp.json()["metadata_url"] == "https://anilist.co/manga/12345"
