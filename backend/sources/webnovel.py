"""Webnovel.com source adapter (stub).

Webnovel sits behind aggressive anti-bot tooling and locks most chapters behind
a paid "coin" system, so a useful scraper needs FlareSolverr (or similar) plus
account/session handling that we don't have yet. This adapter is registered so
the source shows up in the UI and the light-novel content type has a slot,
but every method returns empty for now — wire up the real scraping in a
follow-up once the auth/anti-bot story is settled.
"""
from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter


class WebnovelSource(SourceAdapter):
    name = "webnovel"
    base_url = "https://www.webnovel.com"
    content_type = "lightnovel"
    supports_url = True

    async def search(self, query: str) -> list[SearchResult]:
        return []

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        return []

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        # Light novels package as text/epub rather than CBZ — wiring that up
        # also requires download_service changes, so leave it unimplemented.
        raise NotImplementedError("Webnovel chapter downloads are not implemented yet.")

    async def parse_url(self, url: str) -> SeriesInfo | None:
        return None

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return []
