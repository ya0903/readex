"""wuxiaworld.site source adapter (stub).

Note: this targets wuxiaworld.site, the unofficial mirror — *not* the
original wuxiaworld.com. It's more scrape-friendly than Webnovel but still
needs per-site CSS selectors and a content pipeline that can package text
chapters. Both pieces are out of scope for the initial light-novel landing,
so this adapter is registered as a placeholder and returns empty results
until the real implementation lands.
"""
from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter


class WuxiaWorldSiteSource(SourceAdapter):
    name = "wuxiaworld_site"
    base_url = "https://wuxiaworld.site"
    content_type = "lightnovel"
    supports_url = True

    async def search(self, query: str) -> list[SearchResult]:
        return []

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        return []

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        raise NotImplementedError("wuxiaworld.site chapter downloads are not implemented yet.")

    async def parse_url(self, url: str) -> SeriesInfo | None:
        return None

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return []
