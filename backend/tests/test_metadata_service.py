# readex/backend/tests/test_metadata_service.py
import pytest
from services.metadata_service import MetadataService, MetadataResult


@pytest.fixture
def service():
    return MetadataService()


@pytest.mark.asyncio
async def test_lookup_anilist_found(service, httpx_mock):
    httpx_mock.add_response(
        url="https://graphql.anilist.co",
        json={
            "data": {
                "Media": {
                    "id": 30013,
                    "title": {"english": "One Piece", "romaji": "One Piece"},
                    "description": "A great manga about pirates.",
                    "status": "RELEASING",
                    "coverImage": {"large": "https://img.anilist.co/one-piece.jpg"},
                    "genres": ["Action", "Adventure"],
                    "siteUrl": "https://anilist.co/manga/30013",
                }
            }
        },
    )
    result = await service.lookup_anilist("One Piece")
    assert result is not None
    assert result.title == "One Piece"
    assert result.cover_url == "https://img.anilist.co/one-piece.jpg"
    assert result.status == "ongoing"
    assert result.url == "https://anilist.co/manga/30013"


@pytest.mark.asyncio
async def test_lookup_anilist_not_found(service, httpx_mock):
    httpx_mock.add_response(
        url="https://graphql.anilist.co",
        json={"data": {"Media": None}},
    )
    result = await service.lookup_anilist("xyznonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_from_url_anilist(service, httpx_mock):
    httpx_mock.add_response(
        url="https://graphql.anilist.co",
        json={
            "data": {
                "Media": {
                    "id": 30013,
                    "title": {"english": "One Piece", "romaji": "One Piece"},
                    "description": "Pirates!",
                    "status": "RELEASING",
                    "coverImage": {"large": "https://img.anilist.co/op.jpg"},
                    "genres": ["Action"],
                    "siteUrl": "https://anilist.co/manga/30013",
                }
            }
        },
    )
    result = await service.fetch_from_url("https://anilist.co/manga/30013/One-Piece")
    assert result is not None
    assert result.title == "One Piece"
