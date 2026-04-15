import httpx
import pytest
from sources.mangadex import MangaDexSource
from sources.base import ChapterInfo


@pytest.fixture
def source():
    return MangaDexSource()


def make_search_response(titles):
    return {
        "data": [
            {
                "id": f"id-{i}",
                "attributes": {
                    "title": {"en": title},
                    "status": "ongoing",
                    "contentRating": "safe",
                    "lastChapter": str(i * 100),
                },
                "relationships": [
                    {"type": "cover_art", "id": f"cover-{i}", "attributes": {"fileName": f"cover{i}.jpg"}}
                ],
            }
            for i, title in enumerate(titles)
        ],
    }


def make_feed_response(chapter_numbers):
    return {
        "data": [
            {
                "id": f"ch-{n}",
                "attributes": {
                    "chapter": str(n),
                    "title": f"Chapter {n}",
                    "translatedLanguage": "en",
                    "pages": 20,
                },
            }
            for n in chapter_numbers
        ],
        "total": len(chapter_numbers),
    }


def make_athome_response():
    return {
        "baseUrl": "https://uploads.mangadex.org",
        "chapter": {
            "hash": "abc123",
            "data": ["page1.jpg", "page2.jpg"],
            "dataSaver": ["page1-saver.jpg", "page2-saver.jpg"],
        },
    }


@pytest.mark.asyncio
async def test_search(source, httpx_mock):
    httpx_mock.add_response(json=make_search_response(["One Piece"]))
    results = await source.search("one piece")
    assert len(results) == 1
    assert results[0].title == "One Piece"
    assert results[0].source_name == "mangadex"


@pytest.mark.asyncio
async def test_get_chapters(source, httpx_mock):
    httpx_mock.add_response(json=make_feed_response([1.0, 2.0, 3.0]))
    chapters = await source.get_chapters("test-manga-id")
    assert len(chapters) == 3
    assert chapters[0].chapter_number == 1.0


@pytest.mark.asyncio
async def test_download_chapter(source, httpx_mock):
    httpx_mock.add_response(
        url="https://api.mangadex.org/at-home/server/ch-1",
        json=make_athome_response(),
    )
    httpx_mock.add_response(
        url="https://uploads.mangadex.org/data/abc123/page1.jpg",
        content=b"image-data-1",
    )
    httpx_mock.add_response(
        url="https://uploads.mangadex.org/data/abc123/page2.jpg",
        content=b"image-data-2",
    )

    chapter = ChapterInfo(
        source_chapter_id="ch-1", chapter_number=1.0,
        title="Chapter 1", url="",
    )
    images = await source.download_chapter(chapter)
    assert len(images) == 2
    assert images[0] == b"image-data-1"


@pytest.mark.asyncio
async def test_parse_url_valid(source, httpx_mock):
    httpx_mock.add_response(
        json={
            "data": {
                "id": "manga-123",
                "attributes": {
                    "title": {"en": "Test Manga"},
                    "status": "ongoing",
                },
                "relationships": [],
            }
        }
    )
    info = await source.parse_url("https://mangadex.org/title/manga-123/test-manga")
    assert info is not None
    assert info.source_id == "manga-123"
    assert info.title == "Test Manga"


@pytest.mark.asyncio
async def test_parse_url_invalid(source):
    info = await source.parse_url("https://example.com/not-mangadex")
    assert info is None
