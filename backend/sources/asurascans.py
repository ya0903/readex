"""AsuraScans source adapter — uses FlareSolverr to render Next.js JS pages."""
import re
from urllib.parse import quote_plus, urljoin

import httpx
from selectolax.parser import HTMLParser

from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter
from sources.flaresolverr import flaresolverr_get, is_enabled

BASE = "https://asuracomic.net"
# Search lives on the legacy domain because asuracomic.net's /series route
# only renders trending/featured items regardless of query string.
SEARCH_BASE = "https://asurascans.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SERIES_URL_PATTERN = re.compile(
    r"asura(?:scans?|comic)\.(?:net|com)/(?:series|comics)/([^/?#\s]+)", re.I
)
CHAPTER_URL_PATTERN = re.compile(r"/chapter/(\d+(?:\.\d+)?)")
CHAPTER_NUM_PATTERN = re.compile(r"chapter[\s\-_]*(\d+(?:\.\d+)?)", re.I)
# AsuraScans embeds Astro hydration data — extract series tuples from it.
ASTRO_SERIES_PATTERN = re.compile(
    r'&quot;slug&quot;:\[0,&quot;([^&]+?)&quot;\],&quot;title&quot;:\[0,&quot;([^&]+?)&quot;\],&quot;cover_url&quot;:\[0,&quot;([^&]+?)&quot;\][^}]*?&quot;public_url&quot;:\[0,&quot;([^&]+?)&quot;\]',
    re.DOTALL,
)


def _series_id_from_url(url: str) -> str | None:
    m = SERIES_URL_PATTERN.search(url)
    return m.group(1) if m else None


class AsuraScansSource(SourceAdapter):
    name = "asurascans"
    base_url = BASE
    content_type = "manhwa"
    supports_url = True

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=20.0, follow_redirects=True,
            headers={"User-Agent": UA, "Referer": BASE + "/"},
        )

    async def _fetch_html(self, url: str) -> str | None:
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
        try:
            html = await self._fetch_html(
                f"{SEARCH_BASE}/browse?search={quote_plus(query)}"
            )
            if not html:
                return []
            # AsuraScans renders results from Astro hydration JSON. Extract
            # `slug` + `title` pairs (always adjacent), then resolve each
            # slug to its `/comics/{slug}-{hash}` public URL.
            SLUG_TITLE = re.compile(
                r'&quot;slug&quot;:\[0,&quot;([^&]+?)&quot;\],'
                r'&quot;title&quot;:\[0,&quot;([^&]+?)&quot;\]'
            )
            COVER_AFTER = re.compile(
                r'&quot;cover_url&quot;:\[0,&quot;([^&]+?)&quot;\]'
            )
            STATUS_AFTER = re.compile(
                r'&quot;status&quot;:\[0,&quot;([^&]+?)&quot;\]'
            )
            CHAPTER_COUNT_AFTER = re.compile(
                r'&quot;chapter_count&quot;:\[0,(\d+)\]'
            )
            results: list[SearchResult] = []
            seen: set[str] = set()

            for m in SLUG_TITLE.finditer(html):
                slug = m.group(1)
                title = m.group(2).replace("&#39;", "'").replace("\\u0027", "'")
                pub = re.search(
                    r'/comics/(' + re.escape(slug) + r'-[a-f0-9]+)', html
                )
                if not pub:
                    continue
                sid = pub.group(1)
                if sid in seen:
                    continue
                seen.add(sid)

                # Take a wide window after the slug, then stop at the next
                # slug entry so we don't accidentally grab another series's data.
                tail = html[m.end():m.end() + 4000]
                next_slug = tail.find("&quot;slug&quot;:")
                if next_slug > 0:
                    tail = tail[:next_slug]

                cover = None
                cm = COVER_AFTER.search(tail)
                if cm:
                    cover = cm.group(1)
                status = None
                sm = STATUS_AFTER.search(tail)
                if sm:
                    raw = sm.group(1).strip().lower()
                    status = {
                        "ongoing": "ongoing",
                        "completed": "complete",
                        "complete": "complete",
                        "hiatus": "hiatus",
                        "dropped": "dropped",
                        "cancelled": "dropped",
                        "canceled": "dropped",
                        "season end": "ongoing",
                    }.get(raw, raw)
                ch_count = None
                ccm = CHAPTER_COUNT_AFTER.search(tail)
                if ccm:
                    try:
                        ch_count = int(ccm.group(1))
                    except ValueError:
                        ch_count = None

                results.append(SearchResult(
                    source_name=self.name, source_id=sid, title=title,
                    cover_url=cover, content_type="manhwa",
                    chapter_count=ch_count, status=status,
                    url=urljoin(BASE, f"/comics/{sid}"),
                ))
                if len(results) >= 20:
                    break
            return results
        except Exception:
            return []

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        try:
            html = await self._fetch_html(f"{BASE}/comics/{series_id}")
            if not html:
                return []

            # AsuraScans only renders the latest 3 chapters in the series page
            # HTML — the rest load via JS. But the page metadata blob includes
            # `chapter_count` and the slug, so we can determine the total and
            # generate the URLs `/comics/{series_id}/chapter/{N}` ourselves.
            slug = re.sub(r"-[a-f0-9]+$", "", series_id)
            total = 0
            # Match a slug:title:...:chapter_count tuple anywhere in the page
            # JSON; the chapter_count value can be 100s of chars after the slug.
            slug_chapter_re = re.compile(
                r'&quot;slug&quot;:\[0,&quot;'
                + re.escape(slug)
                + r'&quot;\][\s\S]{0,2000}?&quot;chapter_count&quot;:\[0,(\d+)\]'
            )
            m = slug_chapter_re.search(html)
            if m:
                total = int(m.group(1))
            # Fallback: pick the highest visible chapter number
            visible = sorted({
                float(m.group(1))
                for m in re.finditer(
                    rf"/comics/{re.escape(series_id)}/chapter/(\d+(?:\.\d+)?)",
                    html,
                )
            })
            if total == 0 and visible:
                total = int(max(visible))

            chapters: list[ChapterInfo] = []
            for n in range(1, total + 1):
                num_str = str(n)
                href = f"/comics/{series_id}/chapter/{num_str}"
                chapters.append(ChapterInfo(
                    source_chapter_id=num_str,
                    chapter_number=float(n),
                    title=f"Chapter {n}",
                    # Use SEARCH_BASE (asurascans.com) because the chapter
                    # reader only serves content there — asuracomic.net
                    # redirects chapter URLs to the home page.
                    url=urljoin(SEARCH_BASE, href),
                ))
            chapters.reverse()
            next_num = 1.0
            fixed: list[ChapterInfo] = []
            for ch in chapters:
                n = ch.chapter_number if ch.chapter_number >= 0 else next_num
                fixed.append(ChapterInfo(
                    source_chapter_id=ch.source_chapter_id, chapter_number=n,
                    title=ch.title, url=ch.url,
                ))
                next_num = max(next_num + 1.0, n + 1.0)
            return fixed
        except Exception:
            return []

    async def download_chapter(
        self, chapter: ChapterInfo, progress_cb=None
    ) -> list[bytes]:
        try:
            # The chapter viewer only renders properly on asurascans.com (legacy
            # domain); asuracomic.net/comics/.../chapter/N redirects to the
            # home page for unauthenticated requests.
            url = chapter.url or ""
            if "asuracomic.net" in url:
                url = url.replace("asuracomic.net", "asurascans.com")
            if not url and chapter.source_chapter_id:
                # Fallback: reconstruct from series_id hint isn't available here,
                # but chapter.url should be set by get_chapters()
                url = f"{SEARCH_BASE}/comics/{chapter.source_chapter_id}"

            html = await self._fetch_html(url)
            if not html:
                return []

            # Prefer the `pages` array in Astro hydration JSON — it lists every
            # page URL in order, not just the first few that render in static HTML.
            pages_start = html.find("&quot;pages&quot;:[1,[")
            if pages_start >= 0:
                chunk = html[pages_start:pages_start + 200000]
                all_urls = re.findall(
                    r"&quot;url&quot;:\[0,&quot;([^&]+?)&quot;\]", chunk
                )
                page_urls = [
                    u for u in all_urls if "/asura-images/chapters/" in u
                ]
            else:
                # Fallback: raw URL search (only finds what's statically rendered)
                page_urls = sorted(set(re.findall(
                    r'https?://[^\s"\'<>]+/asura-images/chapters/[^\s"\'<>]+\.(?:webp|jpg|jpeg|png)',
                    html,
                )))

            # Dedupe and sort by page number embedded in the filename
            def _page_num(u: str) -> tuple[int, str]:
                m = re.search(r"/(\d+)\.[a-z]+$", u)
                return (int(m.group(1)) if m else 999, u)
            page_urls.sort(key=_page_num)

            if not page_urls:
                # Nothing to download — don't return unrelated cover images
                return []

            images: list[bytes] = []
            total = len(page_urls)
            if progress_cb:
                try: progress_cb(0, total)
                except Exception: pass
            for i, src in enumerate(page_urls, 1):
                try:
                    r = await self._client.get(src, headers={
                        "User-Agent": UA,
                        "Referer": url,
                        "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
                    })
                    r.raise_for_status()
                    images.append(r.content)
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
            html = await self._fetch_html(f"{BASE}/comics/{sid}")
            if not html:
                return None
            doc = HTMLParser(html)
            t = doc.css_first("h1, h2.text-2xl")
            title = (t.text() or "").strip() if t else sid
            return SeriesInfo(
                source_name=self.name, source_id=sid, title=title,
                cover_url=None, content_type="manhwa", url=f"{BASE}/comics/{sid}",
            )
        except Exception:
            return None

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return await self.get_chapters(series_id)
