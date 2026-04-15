"""MangaKatana source adapter, ported from mangal's MangaKatana.lua.

Search uses a POST to the base URL with form `s=query&search_by=book_name`.
Chapter list is on the manga page in `.uk-table` with `.chapter > a` rows.
Chapter images are listed in a JS variable `thzq=[...]` on the chapter page.
"""
import re
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter

BASE = "https://mangakatana.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Referer": BASE + "/",
    "Accept": "text/html,*/*",
}
SERIES_URL_PATTERN = re.compile(r"mangakatana\.com/manga/([^/?#\s]+)", re.I)
CHAPTER_NUM_PATTERN = re.compile(r"chapter[\s\-_]*(\d+(?:\.\d+)?)", re.I)
THZQ_PATTERN = re.compile(r"var\s+thzq\s*=\s*\[(.*?)\]\s*;", re.DOTALL)


def _series_id_from_url(url: str) -> str | None:
    m = SERIES_URL_PATTERN.search(url)
    return m.group(1) if m else None


class MangaKatanaSource(SourceAdapter):
    name = "mangakatana"
    base_url = BASE
    content_type = "manga"
    supports_url = True

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers=HEADERS
        )

    async def search(self, query: str) -> list[SearchResult]:
        try:
            normalized = query.replace("\u2019", "'")  # smart quote → ascii
            resp = await self._client.post(
                BASE,
                data={"s": normalized, "search_by": "book_name"},
                headers={
                    **HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            resp.raise_for_status()
            doc = HTMLParser(resp.text)
            results: list[SearchResult] = []
            seen: set[str] = set()
            # MangaKatana wraps each result in a `.item` block containing the
            # cover img and a `.text > a` title link.
            for item in doc.css(".item"):
                link = item.css_first(".text > a") or item.css_first("a[href*='/manga/']")
                if not link:
                    continue
                href = link.attributes.get("href") or ""
                if "/manga/" not in href:
                    continue
                full = urljoin(BASE, href)
                sid = _series_id_from_url(full)
                if not sid or sid in seen:
                    continue
                seen.add(sid)

                # Title may be empty on link.text() (cover wraps it); try alt + img title fallbacks
                title = (link.text() or "").strip().replace("\u2019", "'")
                if not title:
                    img_for_title = item.css_first("img")
                    if img_for_title:
                        title = (img_for_title.attributes.get("alt") or "").strip()
                if not title:
                    continue

                # Cover lives directly inside .item
                cover_url = None
                img = item.css_first("img")
                if img:
                    cover_url = (
                        img.attributes.get("src")
                        or img.attributes.get("data-src")
                        or img.attributes.get("data-lazy-src")
                    )
                    if cover_url:
                        cover_url = urljoin(BASE, cover_url)

                results.append(
                    SearchResult(
                        source_name=self.name,
                        source_id=sid,
                        title=title,
                        cover_url=cover_url,
                        content_type="manga",
                        chapter_count=None,
                        status=None,
                        url=full,
                    )
                )
                if len(results) >= 20:
                    break
            return results
        except Exception:
            return []

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        try:
            url = f"{BASE}/manga/{series_id}"
            resp = await self._client.get(url)
            resp.raise_for_status()
            doc = HTMLParser(resp.text)

            chapters: list[ChapterInfo] = []
            seen: set[str] = set()

            # Lua selector: .uk-table .chapter > a
            table = doc.css_first(".uk-table")
            anchors = []
            if table:
                anchors = table.css(".chapter > a")
            if not anchors:
                # Fallback selectors seen in the wild
                anchors = doc.css(".chapter_list .chapter a, .chapters_box a")

            for a in anchors:
                href = a.attributes.get("href") or ""
                if not href or href in seen:
                    continue
                seen.add(href)
                label = (a.text() or "").strip()
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

            chapters.reverse()  # MangaKatana lists newest-first
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

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        try:
            resp = await self._client.get(
                chapter.url, headers={**HEADERS, "Referer": BASE + "/"}
            )
            resp.raise_for_status()
            text = resp.text

            # Lua approach: locate `thzq=[...]` and split entries
            img_urls: list[str] = []
            m = THZQ_PATTERN.search(text)
            if m:
                payload = m.group(1)
                for raw in payload.split(","):
                    raw = raw.strip()
                    if not raw:
                        continue
                    # entries are quoted strings like 'https://...jpg'
                    cleaned = raw.strip().strip("'\"")
                    if cleaned.startswith("http"):
                        img_urls.append(cleaned)

            if not img_urls:
                # HTML fallback: img tags inside the reader
                doc = HTMLParser(text)
                for img in doc.css("#imgs img, .wrap_img img, img.wide"):
                    src = img.attributes.get("src") or img.attributes.get("data-src")
                    if src and src.startswith("http"):
                        img_urls.append(src)

            images: list[bytes] = []
            for src in img_urls:
                try:
                    img_resp = await self._client.get(
                        src, headers={**HEADERS, "Referer": chapter.url}
                    )
                    img_resp.raise_for_status()
                    images.append(img_resp.content)
                except Exception:
                    continue
            return images
        except Exception:
            return []

    async def parse_url(self, url: str) -> SeriesInfo | None:
        sid = _series_id_from_url(url)
        if not sid:
            return None
        try:
            resp = await self._client.get(f"{BASE}/manga/{sid}")
            resp.raise_for_status()
            doc = HTMLParser(resp.text)
            title = None
            for sel in ("h1.heading", ".info h1", "h1", "title"):
                el = doc.css_first(sel)
                if el:
                    t = (el.text() or "").strip()
                    if t:
                        title = t
                        break
            cover = None
            img = doc.css_first(".cover img, .info img")
            if img:
                cover = img.attributes.get("src") or img.attributes.get("data-src")
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
