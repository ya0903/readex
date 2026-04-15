from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
    source_name: str
    source_id: str
    title: str
    cover_url: str | None
    content_type: str  # manga, manhwa, comic
    chapter_count: int | None
    status: str | None  # ongoing, complete
    url: str


@dataclass
class ChapterInfo:
    source_chapter_id: str
    chapter_number: float
    title: str | None
    url: str


@dataclass
class SeriesInfo:
    source_name: str
    source_id: str
    title: str
    cover_url: str | None
    content_type: str
    url: str


class SourceAdapter(ABC):
    name: str
    base_url: str
    content_type: str
    supports_url: bool

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]:
        ...

    @abstractmethod
    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        ...

    @abstractmethod
    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        ...

    @abstractmethod
    async def parse_url(self, url: str) -> SeriesInfo | None:
        ...

    @abstractmethod
    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        ...
