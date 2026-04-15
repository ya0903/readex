from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from main import app
from sources.base import SearchResult, SeriesInfo
from sources.registry import SourceRegistry


@pytest.fixture
def mock_registry():
    registry = SourceRegistry()
    source = AsyncMock()
    source.name = "mangadex"
    source.supports_url = True
    source.search = AsyncMock(return_value=[
        SearchResult(
            source_name="mangadex", source_id="md-1", title="One Piece",
            cover_url=None, content_type="manga", chapter_count=1100,
            status="ongoing", url="https://mangadex.org/title/md-1",
        ),
    ])
    source.parse_url = AsyncMock(return_value=SeriesInfo(
        source_name="mangadex", source_id="md-1", title="One Piece",
        cover_url=None, content_type="manga", url="https://mangadex.org/title/md-1",
    ))
    registry.register(source)
    return registry


@pytest.fixture
def client(mock_registry):
    app.state.source_registry = mock_registry
    yield TestClient(app)


def test_search(client):
    resp = client.post("/api/search", json={"query": "one piece"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "One Piece"


def test_parse_url(client):
    resp = client.post("/api/search/url", json={
        "url": "https://mangadex.org/title/md-1/one-piece"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "One Piece"
    assert data["source_name"] == "mangadex"
