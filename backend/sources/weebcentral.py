"""WeebCentral source adapter, ported from mangal's WCentral.lua."""
import re
from urllib.parse import quote_plus, urljoin

import httpx
from selectolax.parser import HTMLParser

from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter

BASE = "https://weebcentral.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Referer": BASE + "/",
    "Accept": "text/html,*/*",
}
SERIES_URL_PATTERN = re.compile(r"weebcentral\.com/series/([A-Z0-9]+)", re.I)
CHAPTER_NUM_PATTERN = re.compile(r"chapter[\s\-_]*(\d+(?:\.\d+)?)", re.I)


def _series_id_from_url(url: str) -> str | None:
    m = SERIES_URL_PATTERN.search(url)
    return m.group(1) if m else None


class WeebCentralSource(SourceAdapter):
    name = "weebcentral"
    base_url = BASE
    content_type = "manga"
    supports_url = True

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers=HEADERS, verify=False
        )

    async def search(self, query: str) -> list[SearchResult]:
        try:
            url = (
                f"{BASE}/search/data?text={quote_plus(query)}"
                "&limit=32&offset=0&display_mode=Full+Display"
            )
            resp = await self._client.get(url)
            resp.raise_for_status()
            doc = HTMLParser(resp.text)
            results: list[SearchResult] = []
            seen: set[str] = set()
            for a in doc.css("a[href*='/series/']"):
                href = a.attributes.get("href") or ""
                if "/series/" not in href:
                    continue
                sid = _series_id_from_url(href)
                if not sid or sid in seen:
                    continue
                seen.add(sid)

                title = ""
                for d in a.css("div"):
                    t = (d.text() or "").strip()
                    if t:
                        title = t
                if not title:
                    title = (a.text() or "").strip()
                if not title:
                    continue

                cover_url = None
                img = a.css_first("img")
                if img:
                    cover_url = img.attributes.get("src") or img.attributes.get("data-src")

                results.append(
                    SearchResult(
                        source_name=self.name,
                        source_id=sid,
                        title=title,
                        cover_url=cover_url,
                        content_type="manga",
                        chapter_count=None,
                        status=None,
                        url=urljoin(BASE, href),
                    )
                )
                if len(results) >= 20:
                    break
            return results
        except Exception:
            return []

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        try:
            resp = await self._client.get(f"{BASE}/series/{series_id}")
            resp.raise_for_status()
            canonical = str(resp.url).rstrip("/")
            list_url = f"{canonical}/full-chapter-list"
            list_resp = await self._client.get(
                list_url, headers={**HEADERS, "Referer": canonical}
            )
            list_resp.raise_for_status()
            doc = HTMLParser(list_resp.text)

            chapters: list[ChapterInfo] = []
            seen: set[str] = set()
            for a in doc.css("a[href*='/chapters/']"):
                href = a.attributes.get("href") or ""
                if "/chapters/" not in href or href in seen:
                    continue
                seen.add(href)
                # Pull just the first non-empty span/text that looks like a chapter title
                label = ""
                for span in a.css("span"):
                    t = (span.text() or "").strip()
                    if t and "Last Read" not in t:
                        label = t
                        break
                if not label:
                    raw = (a.text() or "").strip()
                    # Take only the first line, skip trailing JS/CSS noise
                    label = raw.split("\n")[0].strip() if raw else ""
                num = None
                m = CHAPTER_NUM_PATTERN.search(label) if label else None
                if m:
                    num = float(m.group(1))
                chapters.append(
                    ChapterInfo(
                        source_chapter_id=href.rstrip("/").split("/")[-1],
                        chapter_number=num if num is not None else -1.0,
                        title=label or None,
                        url=urljoin(BASE, href),
                    )
                )

            chapters.reverse()  # newest-first → oldest-first
            next_num = 1.0
            fixed: list[ChapterInfo] = []
            for ch in chapters:
                n = ch.chapter_number if ch.chapter_number >= 0 else next_num
                fixed.append(
                    ChapterInfo(
                        source_chapter_id=ch.source_chapter_id,
                        chapter_number=n,
                        title=ch.title,
                        url=ch.url,
                    )
                )
                next_num = max(next_num + 1.0, n + 1.0)
            return fixed
        except Exception:
            return []

    async def download_chapter(
        self, chapter: ChapterInfo, progress_cb=None
    ) -> list[bytes]:
        try:
            # WeebCentral renders the page client-side via HTMX. The page list
            # is served at /chapters/{id}/images as fragment HTML.
            # Prefer source_chapter_id (always present) over url (empty when
            # called from the background worker).
            chapter_id = chapter.source_chapter_id or (
                chapter.url.rstrip("/").split("/")[-1] if chapter.url else ""
            )
            if not chapter_id:
                return []
            chapter_page = f"{BASE}/chapters/{chapter_id}"
            images_url = (
                f"{BASE}/chapters/{chapter_id}/images"
                "?is_prev=False&reading_style=long_strip"
            )
            resp = await self._client.get(
                images_url, headers={**HEADERS, "Referer": chapter_page}
            )
            resp.raise_for_status()
            doc = HTMLParser(resp.text)

            img_urls: list[str] = []
            for img in doc.css("img"):
                src = img.attributes.get("src") or ""
                # Skip placeholders / brand
                if not src or "broken_image" in src or "/static/" in src:
                    continue
                if any(
                    src.lower().endswith(ext)
                    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")
                ):
                    img_urls.append(src)

            images: list[bytes] = []
            total = len(img_urls)
            if progress_cb:
                try: progress_cb(0, total)
                except Exception: pass
            for i, src in enumerate(img_urls, 1):
                try:
                    img_resp = await self._client.get(
                        src,
                        headers={
                            **HEADERS,
                            "Referer": chapter_page,
                            "Accept": "image/avif,image/webp,image/png,image/*,*/*",
                        },
                    )
                    img_resp.raise_for_status()
                    images.append(img_resp.content)
                except Exception:
                    pass
                if progress_cb:
                    try: progress_cb(i, total)
                    except Exception: pass
            return images
        except Exception:
            return []

    async def parse_url(self, url: str) -> SeriesInfo | None:
        sid = _series_id_from_url(url)
        if not sid:
            return None
        try:
            resp = await self._client.get(f"{BASE}/series/{sid}")
            resp.raise_for_status()
            doc = HTMLParser(resp.text)
            title = None
            for sel in ("h1", "title"):
                el = doc.css_first(sel)
                if el:
                    t = (el.text() or "").strip()
                    if t:
                        title = t
                        break
            cover = None
            img = doc.css_first("img[alt*='cover'], main img")
            if img:
                cover = img.attributes.get("src")
            return SeriesInfo(
                source_name=self.name,
                source_id=sid,
                title=title or sid,
                cover_url=cover,
                content_type="manga",
                url=str(resp.url),
            )
        except Exception:
            return None

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return await self.get_chapters(series_id)
