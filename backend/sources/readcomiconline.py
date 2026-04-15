import re
import httpx
from selectolax.parser import HTMLParser
from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter

# NOTE: ReadComicOnline uses heavy JavaScript to render image URLs.
# The image URLs are typically obfuscated or loaded via AJAX after the initial page load.
# A full implementation requires Playwright or a similar headless browser.
# This scaffold implements the structure and static HTML parsing where possible.

SERIES_URL_RE = re.compile(r"readcomiconline\.li/Comic/([^/?#\s]+)")


class ReadComicOnlineSource(SourceAdapter):
    name = "readcomiconline"
    base_url = "https://readcomiconline.li"
    content_type = "comic"
    supports_url = True

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://readcomiconline.li/",
            },
        )

    async def search(self, query: str) -> list[SearchResult]:
        try:
            resp = await self._client.get(f"{self.base_url}/Search/Comic", params={"keyword": query})
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            results = []
            # Search results are listed in .list-comic or similar containers
            for card in tree.css("div.list-comic > div, li.list-item, div.comic-item"):
                link = card.css_first("a[href*='/Comic/']")
                if not link:
                    continue
                href = link.attributes.get("href", "")
                title_node = card.css_first("p, span, h3, h2, a.title")
                title = title_node.text(strip=True) if title_node else link.text(strip=True)
                if not title or not href:
                    continue
                img_node = card.css_first("img")
                cover_url = img_node.attributes.get("src") or img_node.attributes.get("data-src") if img_node else None
                if cover_url and cover_url.startswith("/"):
                    cover_url = f"{self.base_url}{cover_url}"
                series_match = SERIES_URL_RE.search(href if href.startswith("http") else f"{self.base_url}{href}")
                series_id = series_match.group(1) if series_match else href.rstrip("/").split("/Comic/")[-1]
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
            resp = await self._client.get(f"{self.base_url}/Comic/{series_id}")
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            chapters = []
            # Chapter list: ul.list-chapters li a or similar
            for item in tree.css("ul.list-chapters li a, div.chapters li a, a[href*='/Comic/'][href*='/Issue-']"):
                href = item.attributes.get("href", "")
                if not href:
                    continue
                text = item.text(strip=True)
                # Extract issue number from href like /Comic/SeriesName/Issue-12
                num_match = re.search(r"Issue-(\d+(?:\.\d+)?)", href, re.IGNORECASE)
                if num_match:
                    chapter_number = float(num_match.group(1))
                else:
                    num_match = re.search(r"(\d+(?:\.\d+)?)\s*$", text)
                    chapter_number = float(num_match.group(1)) if num_match else 0.0
                ch_id = href.rstrip("/").split("/")[-1]
                chapters.append(ChapterInfo(
                    source_chapter_id=ch_id,
                    chapter_number=chapter_number,
                    title=text or None,
                    url=href if href.startswith("http") else f"{self.base_url}{href}",
                ))
            chapters.sort(key=lambda c: c.chapter_number)
            return chapters
        except Exception:
            return []

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        """
        NOTE: ReadComicOnline uses JavaScript obfuscation to generate image URLs.
        The images are loaded via AJAX or decoded from obfuscated JS after page load.
        A complete implementation requires Playwright or Selenium.

        This scaffold attempts basic static extraction but will likely return an
        empty list for most chapters. To fully implement, replace this method
        with a Playwright-based solution that evaluates the page JS and extracts
        the decoded image URLs.
        """
        try:
            resp = await self._client.get(chapter.url)
            resp.raise_for_status()

            # Attempt 1: look for image URLs in a JS array (sometimes present in page source)
            img_array_match = re.search(
                r'lstImages\.push\("([^"]+)"\)|"(https?://[^"]+\.(?:jpg|jpeg|png|webp))"',
                resp.text,
                re.IGNORECASE,
            )
            images = []

            # Collect all potential image URLs from JS source
            url_matches = re.findall(
                r'(?:lstImages\.push\(|src\s*=\s*)"(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                resp.text,
                re.IGNORECASE,
            )
            for img_url in url_matches:
                try:
                    img_resp = await self._client.get(img_url)
                    if img_resp.status_code == 200:
                        images.append(img_resp.content)
                except Exception:
                    continue

            if images:
                return images

            # Attempt 2: static HTML img tags (unlikely to work due to JS rendering)
            tree = HTMLParser(resp.text)
            for img in tree.css("div#divImage img, div.chapter-images img, img#imgCurrent"):
                src = img.attributes.get("src", "")
                if not src or not src.startswith("http"):
                    continue
                try:
                    img_resp = await self._client.get(src)
                    if img_resp.status_code == 200:
                        images.append(img_resp.content)
                except Exception:
                    continue

            return images
        except Exception:
            return []

    async def parse_url(self, url: str) -> SeriesInfo | None:
        match = SERIES_URL_RE.search(url)
        if not match:
            return None
        series_id = match.group(1)
        try:
            resp = await self._client.get(f"{self.base_url}/Comic/{series_id}")
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            title_node = tree.css_first("h2.barTitle, h1, .comic-title")
            title = title_node.text(strip=True) if title_node else series_id
            img_node = tree.css_first("img.barImage, div.cover img, img[class*='cover']")
            cover_url = img_node.attributes.get("src") if img_node else None
            if cover_url and cover_url.startswith("/"):
                cover_url = f"{self.base_url}{cover_url}"
            return SeriesInfo(
                source_name=self.name,
                source_id=series_id,
                title=title,
                cover_url=cover_url,
                content_type=self.content_type,
                url=f"{self.base_url}/Comic/{series_id}",
            )
        except Exception:
            return None

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return await self.get_chapters(series_id)
