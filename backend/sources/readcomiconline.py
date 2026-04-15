"""ReadComicOnline source adapter.

readcomiconline.li is sits behind Cloudflare and pages don't render any chapter
data from plain httpx when hit from a homelab/server IP — the response is a
challenge page. We route HTML fetches through FlareSolverr when configured so
the chapter list and image pages render. Image downloads themselves still go
through httpx since they come from cached CDNs that don't require a challenge.
"""
import re
import httpx
from selectolax.parser import HTMLParser
from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter
from sources.flaresolverr import flaresolverr_get, is_enabled

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

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch a page as rendered HTML. Prefers FlareSolverr when configured
        because readcomiconline.li blocks direct server-side requests with a
        Cloudflare challenge. Falls back to httpx so local dev still works.
        """
        if is_enabled():
            html = await flaresolverr_get(url)
            if html:
                return html
        try:
            r = await self._client.get(url)
            if r.status_code < 400:
                return r.text
        except Exception:
            pass
        return None

    async def search(self, query: str) -> list[SearchResult]:
        html = await self._fetch_html(
            f"{self.base_url}/Search/Comic?keyword={query.replace(' ', '+')}"
        )
        if not html:
            return []
        tree = HTMLParser(html)
        results: list[SearchResult] = []
        # Search results are `<div class="item">` cards. Each card contains an
        # `<a href="/Comic/…">` with an `<img>` cover and a `<span class="title">`.
        for card in tree.css("div.item"):
            link = card.css_first("a[href^='/Comic/']")
            if not link:
                continue
            href = link.attributes.get("href", "")
            if "/Issue-" in href:
                continue
            title_node = card.css_first("span.title") or link
            title = title_node.text(strip=True)
            if not title or not href:
                continue
            img_node = card.css_first("img")
            cover_url = img_node.attributes.get("src") if img_node else None
            if cover_url and cover_url.startswith("/"):
                cover_url = f"{self.base_url}{cover_url}"
            series_id = href.rstrip("/").split("/Comic/")[-1].split("?")[0]
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
        # Dedupe by series_id while preserving order
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for r in results:
            if r.source_id in seen:
                continue
            seen.add(r.source_id)
            deduped.append(r)
        return deduped

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        html = await self._fetch_html(f"{self.base_url}/Comic/{series_id}")
        if not html:
            return []
        tree = HTMLParser(html)
        chapters: list[ChapterInfo] = []
        # Chapter list lives in `table.listing` → each row has an anchor to
        # `/Comic/{series}/Issue-{n}?id={id}`.
        for item in tree.css("table.listing a[href*='/Issue-']"):
            href = item.attributes.get("href", "")
            if not href:
                continue
            text = item.text(strip=True)
            num_match = re.search(r"Issue-(\d+(?:\.\d+)?)", href, re.IGNORECASE)
            if num_match:
                chapter_number = float(num_match.group(1))
            else:
                num_match = re.search(r"(\d+(?:\.\d+)?)\s*$", text)
                chapter_number = float(num_match.group(1)) if num_match else 0.0
            # source_chapter_id: keep the full "Issue-N?id=XXXX" so we can
            # rebuild the chapter URL deterministically later.
            ch_id = href.rstrip("/").split("/")[-1]
            chapters.append(ChapterInfo(
                source_chapter_id=ch_id,
                chapter_number=chapter_number,
                title=text or None,
                url=href if href.startswith("http") else f"{self.base_url}{href}",
            ))
        # Site lists newest-first; we want oldest-first for reading order.
        chapters.sort(key=lambda c: c.chapter_number)
        return chapters

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        """Fetch a chapter's image list via FlareSolverr (the page needs JS to
        inject the lstImages array), then download each image with httpx.

        The reader page also supports `&quality=hq&readType=1` which forces
        all images into a single HTML page rather than paginated — that's what
        lets us pull every image URL from one fetch.
        """
        reader_url = chapter.url
        if "readType=" not in reader_url:
            sep = "&" if "?" in reader_url else "?"
            reader_url = f"{reader_url}{sep}quality=hq&readType=1"

        html = await self._fetch_html(reader_url)
        if not html:
            return []

        # Images are pushed into a JS array: `lstImages.push("https://...")`
        url_matches = re.findall(
            r'lstImages\.push\(\s*"([^"]+)"\s*\)',
            html,
        )
        images: list[bytes] = []
        for img_url in url_matches:
            try:
                img_resp = await self._client.get(img_url)
                if img_resp.status_code == 200 and img_resp.content:
                    images.append(img_resp.content)
            except Exception:
                continue
        return images

    async def parse_url(self, url: str) -> SeriesInfo | None:
        match = SERIES_URL_RE.search(url)
        if not match:
            return None
        series_id = match.group(1)
        html = await self._fetch_html(f"{self.base_url}/Comic/{series_id}")
        if not html:
            return None
        tree = HTMLParser(html)
        title_node = tree.css_first("a.bigChar, h2.barTitle, h1, .comic-title")
        title = title_node.text(strip=True) if title_node else series_id
        img_node = tree.css_first("div.rightBox img, div.barContent img, img.barImage")
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

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return await self.get_chapters(series_id)
