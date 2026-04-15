import re
import httpx
from selectolax.parser import HTMLParser
from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter

SERIES_URL_RE = re.compile(r"mangapill\.com/manga/([^/?#\s]+)")


class MangaPillSource(SourceAdapter):
    name = "mangapill"
    base_url = "https://mangapill.com"
    content_type = "manga"
    supports_url = True

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )

    async def search(self, query: str) -> list[SearchResult]:
        try:
            resp = await self._client.get(f"{self.base_url}/search", params={"q": query})
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            results = []
            # MangaPill search results: cards with /manga/{id} links
            for card in tree.css("div.manga-item, div.grid > div, a[href*='/manga/']"):
                href = card.attributes.get("href", "")
                if not href:
                    link = card.css_first("a[href*='/manga/']")
                    if link:
                        href = link.attributes.get("href", "")
                if not href or "/manga/" not in href:
                    continue
                title_node = card.css_first("strong, .title, h3, div.mt-3")
                title = title_node.text(strip=True) if title_node else ""
                if not title:
                    continue
                img_node = card.css_first("img")
                cover_url = img_node.attributes.get("data-src") or img_node.attributes.get("src") if img_node else None
                # Extract numeric ID + slug: /manga/12345/slug-name
                series_match = SERIES_URL_RE.search(href if href.startswith("http") else f"{self.base_url}{href}")
                series_id = series_match.group(1) if series_match else href.strip("/").split("/manga/")[-1]
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                results.append(SearchResult(
                    source_name=self.name,
                    source_id=series_id,
                    title=title,
                    cover_url=cover_url,
                    content_type=self.content_type,
                    chapter_count=None,
                    status=None,
                    url=full_url,
                ))
            return results
        except Exception:
            return []

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        try:
            resp = await self._client.get(f"{self.base_url}/manga/{series_id}")
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            chapters = []
            seen_ids: set[str] = set()
            seen_nums: set[float] = set()
            # MangaPill: chapter links in #chapters container. The same chapter
            # link sometimes appears multiple times (main list + nav arrows),
            # so dedupe both by source_chapter_id and chapter_number.
            for item in tree.css("#chapters a, div#chapters a, a[href*='/chapters/']"):
                href = item.attributes.get("href", "")
                if not href:
                    continue
                text = item.text(strip=True)
                num_match = re.search(r"(?:chapter|ch\.?)\s*([\d.]+)", text, re.IGNORECASE)
                if num_match:
                    chapter_number = float(num_match.group(1))
                else:
                    url_match = re.search(r"/chapters/([\d.]+)", href)
                    chapter_number = float(url_match.group(1)) if url_match else 0.0
                ch_id = href.rstrip("/").split("/")[-1]
                if ch_id in seen_ids or chapter_number in seen_nums:
                    continue
                seen_ids.add(ch_id)
                seen_nums.add(chapter_number)
                chapters.append(ChapterInfo(
                    source_chapter_id=ch_id,
                    chapter_number=chapter_number,
                    title=None,
                    url=href if href.startswith("http") else f"{self.base_url}{href}",
                ))
            chapters.sort(key=lambda c: c.chapter_number)
            return chapters
        except Exception:
            return []

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        try:
            resp = await self._client.get(chapter.url)
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            images = []
            # MangaPill: images have class js-page
            for img in tree.css("img.js-page, chapter-page img, div.chapter-images img"):
                src = img.attributes.get("data-src") or img.attributes.get("src", "")
                if not src or not src.startswith("http"):
                    continue
                img_resp = await self._client.get(src)
                if img_resp.status_code == 200:
                    images.append(img_resp.content)
            return images
        except Exception:
            return []

    async def parse_url(self, url: str) -> SeriesInfo | None:
        match = SERIES_URL_RE.search(url)
        if not match:
            return None
        series_id = match.group(1)
        try:
            resp = await self._client.get(f"{self.base_url}/manga/{series_id}")
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            title_node = tree.css_first("h1, h2, .manga-title")
            title = title_node.text(strip=True) if title_node else series_id
            img_node = tree.css_first("img.cover, div.cover img, img[class*='cover']")
            cover_url = img_node.attributes.get("data-src") or img_node.attributes.get("src") if img_node else None
            return SeriesInfo(
                source_name=self.name,
                source_id=series_id,
                title=title,
                cover_url=cover_url,
                content_type=self.content_type,
                url=f"{self.base_url}/manga/{series_id}",
            )
        except Exception:
            return None

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return await self.get_chapters(series_id)
