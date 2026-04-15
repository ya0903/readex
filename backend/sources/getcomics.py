import io
import re
import zipfile
import httpx
import rarfile
from selectolax.parser import HTMLParser
from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter

SERIES_URL_RE = re.compile(r"getcomics\.org/(?:comics/)?([^/?#\s]+)")
# Patterns for direct download links on GetComics pages
DOWNLOAD_LINK_RE = re.compile(r'href="(https?://[^"]+\.(?:cbr|cbz|zip|rar))"', re.IGNORECASE)


class GetComicsSource(SourceAdapter):
    name = "getcomics"
    base_url = "https://getcomics.org"
    content_type = "comic"
    supports_url = True

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )

    async def search(self, query: str) -> list[SearchResult]:
        try:
            resp = await self._client.get(f"{self.base_url}/", params={"s": query})
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            results = []
            # GetComics search results: article posts
            for article in tree.css("article, div.post, div.blog-item"):
                link = article.css_first("h1 a, h2 a, h3 a, .post-title a")
                if not link:
                    continue
                href = link.attributes.get("href", "")
                title = link.text(strip=True)
                if not title or not href:
                    continue
                img_node = article.css_first("img")
                cover_url = img_node.attributes.get("src") or img_node.attributes.get("data-src") if img_node else None
                # Use the URL slug as series_id
                series_id = href.rstrip("/").split("/")[-1]
                results.append(SearchResult(
                    source_name=self.name,
                    source_id=series_id,
                    title=title,
                    cover_url=cover_url,
                    content_type=self.content_type,
                    chapter_count=None,
                    status=None,
                    url=href,
                ))
            return results
        except Exception:
            return []

    async def get_chapters(self, series_id: str) -> list[ChapterInfo]:
        """
        GetComics is not a typical series site; each post is typically one issue.
        We model each post as a 'chapter' (issue). For a given series slug,
        we try to search and return matching posts.
        """
        try:
            resp = await self._client.get(f"{self.base_url}/", params={"s": series_id.replace("-", " ")})
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            chapters = []
            for article in tree.css("article, div.post, div.blog-item"):
                link = article.css_first("h1 a, h2 a, h3 a, .post-title a")
                if not link:
                    continue
                href = link.attributes.get("href", "")
                title = link.text(strip=True)
                if not title or not href:
                    continue
                # Try to extract issue number from title
                num_match = re.search(r"#\s*(\d+)|vol\.?\s*(\d+)|issue\s*(\d+)", title, re.IGNORECASE)
                if num_match:
                    chapter_number = float(next(g for g in num_match.groups() if g is not None))
                else:
                    chapter_number = 0.0
                ch_id = href.rstrip("/").split("/")[-1]
                chapters.append(ChapterInfo(
                    source_chapter_id=ch_id,
                    chapter_number=chapter_number,
                    title=title,
                    url=href,
                ))
            chapters.sort(key=lambda c: c.chapter_number)
            return chapters
        except Exception:
            return []

    async def download_chapter(self, chapter: ChapterInfo) -> list[bytes]:
        """
        Download the CBR/CBZ/ZIP file from the GetComics post, unzip it,
        and return individual image bytes. Returns a single bytes entry if
        extraction fails, or individual image bytes if successful.
        """
        try:
            resp = await self._client.get(chapter.url)
            resp.raise_for_status()

            # Find direct download links in the page
            download_links = DOWNLOAD_LINK_RE.findall(resp.text)
            if not download_links:
                # Also check for GetComics-style download buttons
                tree = HTMLParser(resp.text)
                for btn in tree.css("a[href*='download'], a.aio-button, a[class*='download']"):
                    href = btn.attributes.get("href", "")
                    if href and any(ext in href.lower() for ext in (".cbr", ".cbz", ".zip", ".rar")):
                        download_links.append(href)

            if not download_links:
                return []

            # Download the first available file
            file_url = download_links[0]
            file_resp = await self._client.get(file_url)
            file_resp.raise_for_status()
            file_bytes = file_resp.content

            # Attempt to unpack the archive (ZIP/CBZ or RAR/CBR) and extract images
            images = _extract_images_from_archive(file_bytes)
            return images
        except Exception:
            return []

    async def parse_url(self, url: str) -> SeriesInfo | None:
        match = SERIES_URL_RE.search(url)
        if not match:
            return None
        series_id = match.group(1)
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            title_node = tree.css_first("h1, h2.post-title, .entry-title")
            title = title_node.text(strip=True) if title_node else series_id
            img_node = tree.css_first("img.featured, div.post img, .entry-content img")
            cover_url = img_node.attributes.get("src") if img_node else None
            return SeriesInfo(
                source_name=self.name,
                source_id=series_id,
                title=title,
                cover_url=cover_url,
                content_type=self.content_type,
                url=url,
            )
        except Exception:
            return None

    async def check_updates(self, series_id: str) -> list[ChapterInfo]:
        return await self.get_chapters(series_id)


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def _extract_images_from_archive(data: bytes) -> list[bytes]:
    """Extract image files from a ZIP/CBZ or RAR/CBR archive.

    Tries ZIP first (since CBZ/ZIP is most common on GetComics), then falls
    back to RAR. Returns an empty list if neither format parses — callers
    should treat that as "no pages" and surface an error, never write the
    raw archive bytes back as a fake image.
    """
    # Try ZIP/CBZ
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            image_names = sorted(
                name for name in zf.namelist()
                if any(name.lower().endswith(ext) for ext in IMAGE_EXTS)
            )
            if image_names:
                return [zf.read(name) for name in image_names]
    except zipfile.BadZipFile:
        pass
    except Exception:
        pass

    # Try RAR/CBR
    try:
        with rarfile.RarFile(io.BytesIO(data)) as rf:
            image_names = sorted(
                info.filename for info in rf.infolist()
                if not info.is_dir() and any(info.filename.lower().endswith(ext) for ext in IMAGE_EXTS)
            )
            if image_names:
                return [rf.read(name) for name in image_names]
    except rarfile.Error:
        pass
    except Exception:
        pass

    return []
