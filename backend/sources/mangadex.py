import re
import httpx
from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter

API_BASE = "https://api.mangadex.org"
MANGADEX_URL_PATTERN = re.compile(r"mangadex\.org/title/([^/\s]+)")


class MangaDexSource(SourceAdapter):
    name = "mangadex"
    base_url = "https://mangadex.org"
    content_type = "manga"
    supports_url = True

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=30.0)

    async def search(self, query: str) -> list[SearchResult]:
        resp = await self._client.get(f"{API_BASE}/manga", params={
            "title": query,
            "limit": "20",
            "includes[]": "cover_art",
            "contentRating[]": ["safe", "suggestive"],
        })
        resp.raise_for_status()
        data = resp.json()

        results = []
        for manga in data.get("data", []):
            attrs = manga["attributes"]
            title = attrs["title"].get("en") or next(iter(attrs["title"].values()), "Unknown")
            cover_file = None
            for rel in manga.get("relationships", []):
                if rel["type"] == "cover_art" and "attributes" in rel:
                    cover_file = rel["attributes"].get("fileName")

            cover_url = None
            if cover_file:
                cover_url = f"https://uploads.mangadex.org/covers/{manga['id']}/{cover_file}.256.jpg"

            results.append(SearchResult(
                source_name=self.name,
                source_id=manga["id"],
                title=title,
                cover_url=cover_url,
                content_type="manga",
                chapter_count=int(attrs.get("lastChapter") or 0) if attrs.get("lastChapter") else None,
                status=attrs.get("status"),
                url=f"https://mangadex.org/title/{manga['id']}",
            ))
        return results

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        chapters = []
        offset = 0
        limit = 100
        while True:
            resp = await self._client.get(f"{API_BASE}/manga/{series_id}/feed", params={
                "translatedLanguage[]": "en",
                "order[chapter]": "asc",
                "limit": str(limit),
                "offset": str(offset),
            })
            resp.raise_for_status()
            data = resp.json()

            for ch in data.get("data", []):
                attrs = ch["attributes"]
                ch_num = attrs.get("chapter")
                if ch_num is None:
                    continue
                chapters.append(ChapterInfo(
                    source_chapter_id=ch["id"],
                    chapter_number=float(ch_num),
                    title=attrs.get("title"),
                    url=f"https://mangadex.org/chapter/{ch['id']}",
                ))

            if offset + limit >= data.get("total", 0):
                break
            offset += limit

        return chapters

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        resp = await self._client.get(f"{API_BASE}/at-home/server/{chapter.source_chapter_id}")
        resp.raise_for_status()
        data = resp.json()

        base_url = data["baseUrl"]
        ch_hash = data["chapter"]["hash"]
        filenames = data["chapter"]["data"]

        images = []
        for filename in filenames:
            img_resp = await self._client.get(f"{base_url}/data/{ch_hash}/{filename}")
            img_resp.raise_for_status()
            images.append(img_resp.content)

        return images

    async def parse_url(self, url: str) -> SeriesInfo | None:
        match = MANGADEX_URL_PATTERN.search(url)
        if not match:
            return None

        manga_id = match.group(1)
        resp = await self._client.get(f"{API_BASE}/manga/{manga_id}")
        resp.raise_for_status()
        data = resp.json()["data"]
        attrs = data["attributes"]
        title = attrs["title"].get("en") or next(iter(attrs["title"].values()), "Unknown")

        return SeriesInfo(
            source_name=self.name,
            source_id=manga_id,
            title=title,
            cover_url=None,
            content_type="manga",
            url=f"https://mangadex.org/title/{manga_id}",
        )

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return await self.get_chapters(series_id)
