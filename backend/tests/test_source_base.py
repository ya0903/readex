from sources.base import SourceAdapter, SearchResult, ChapterInfo, SeriesInfo
from sources.registry import SourceRegistry


class FakeSource(SourceAdapter):
    name = "fake"
    base_url = "https://fake.com"
    content_type = "manga"
    supports_url = False

    async def search(self, query: str) -> list[SearchResult]:
        return [SearchResult(
            source_name=self.name,
            source_id="fake-1",
            title="Fake Manga",
            cover_url=None,
            content_type="manga",
            chapter_count=10,
            status="ongoing",
            url="https://fake.com/manga/fake-1",
        )]

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        return [ChapterInfo(
            source_chapter_id="ch1",
            chapter_number=1.0,
            title="Chapter 1",
            url="https://fake.com/chapter/ch1",
        )]

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        return [b"fake-image-data"]

    async def parse_url(self, url: str) -> SeriesInfo | None:
        return None

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return []


import pytest


@pytest.mark.asyncio
async def test_fake_source_search():
    source = FakeSource()
    results = await source.search("fake")
    assert len(results) == 1
    assert results[0].title == "Fake Manga"
    assert results[0].source_name == "fake"


@pytest.mark.asyncio
async def test_fake_source_get_chapters():
    source = FakeSource()
    chapters = await source.get_chapters("fake-1")
    assert len(chapters) == 1
    assert chapters[0].chapter_number == 1.0


@pytest.mark.asyncio
async def test_fake_source_download_chapter():
    source = FakeSource()
    chapters = await source.get_chapters("fake-1")
    images = await source.download_chapter(chapters[0])
    assert len(images) == 1
    assert images[0] == b"fake-image-data"


def test_registry_register_and_get():
    registry = SourceRegistry()
    source = FakeSource()
    registry.register(source)
    assert registry.get("fake") is source
    assert "fake" in registry.list_sources()


def test_registry_get_unknown_returns_none():
    registry = SourceRegistry()
    assert registry.get("nonexistent") is None


@pytest.mark.asyncio
async def test_registry_search_all():
    registry = SourceRegistry()
    registry.register(FakeSource())
    results = await registry.search_all("fake")
    assert len(results) == 1
    assert results[0].source_name == "fake"
