"""Metadata enrichment from AniList (GraphQL), MyAnimeList (via Jikan v4),
and Anime-Planet (HTML scrape).
"""
import asyncio
import difflib
import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin

import httpx
from selectolax.parser import HTMLParser


def _normalize_title(t: str) -> str:
    """Lowercase, strip punctuation/spaces — for fuzzy comparison."""
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def _title_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio with a containment bonus.

    Both inputs should already be normalised. Returns 0..1.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Exact substring containment is a strong signal
    if a in b or b in a:
        return max(0.85, len(a) / max(len(a), len(b)))
    return difflib.SequenceMatcher(None, a, b).ratio()

ANILIST_URL = "https://graphql.anilist.co"
# Accept both manga and anime URLs — anime URLs trigger a title-based manga
# lookup (people often paste the anime page by mistake).
ANILIST_URL_PATTERN = re.compile(r"anilist\.co/(manga|anime)/(\d+)(?:/([^?\s/#]+))?")

JIKAN_URL = "https://api.jikan.moe/v4"
MAL_URL_PATTERN = re.compile(r"myanimelist\.net/manga/(\d+)")

AP_BASE = "https://www.anime-planet.com"
AP_URL_PATTERN = re.compile(r"anime-planet\.com/manga/([a-z0-9\-]+)", re.I)
AP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SEARCH_QUERY = """
query ($search: String) {
  Media(search: $search, type: MANGA) {
    id title { english romaji } description status
    coverImage { large } genres siteUrl
  }
}
"""

ID_QUERY = """
query ($id: Int) {
  Media(id: $id, type: MANGA) {
    id title { english romaji } description status
    coverImage { large } genres siteUrl
  }
}
"""

ANILIST_STATUS_MAP = {
    "RELEASING": "ongoing", "FINISHED": "complete",
    "NOT_YET_RELEASED": "ongoing", "CANCELLED": "complete", "HIATUS": "ongoing",
}

MAL_STATUS_MAP = {
    "Publishing": "ongoing",
    "Finished": "complete",
    "On Hiatus": "ongoing",
    "Discontinued": "complete",
    "Not yet published": "ongoing",
}


@dataclass
class MetadataResult:
    title: str
    description: str | None
    status: str
    cover_url: str | None
    genres: list[str]
    url: str


async def _get_with_retry(
    client: httpx.AsyncClient, url: str, retries: int = 2, **kwargs
) -> httpx.Response:
    """GET with backoff for transient 5xx / network errors."""
    last_exc: Exception | None = None
    for i in range(retries + 1):
        try:
            r = await client.get(url, **kwargs)
            if r.status_code < 500:
                return r
            last_exc = httpx.HTTPStatusError(
                f"{r.status_code} from upstream", request=r.request, response=r
            )
        except httpx.HTTPError as e:
            last_exc = e
        if i < retries:
            await asyncio.sleep(0.5 * (2 ** i))
    if last_exc:
        raise last_exc
    return r


def _ap_status(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("complete", "finished", "ended")):
        return "complete"
    return "ongoing"


class MetadataService:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)

    # ---- AniList ----

    def _parse_anilist_media(self, media: dict | None) -> MetadataResult | None:
        if media is None:
            return None
        title = media["title"].get("english") or media["title"].get("romaji") or "Unknown"
        return MetadataResult(
            title=title,
            description=media.get("description"),
            status=ANILIST_STATUS_MAP.get(media.get("status", ""), "ongoing"),
            cover_url=media.get("coverImage", {}).get("large"),
            genres=media.get("genres", []),
            url=media.get("siteUrl", ""),
        )

    async def lookup_anilist(self, title: str) -> MetadataResult | None:
        resp = await self._client.post(
            ANILIST_URL,
            json={"query": SEARCH_QUERY, "variables": {"search": title}},
        )
        resp.raise_for_status()
        media = resp.json().get("data", {}).get("Media")
        return self._parse_anilist_media(media)

    # ---- MyAnimeList (via Jikan) ----

    def _parse_mal_data(self, data: dict | None) -> MetadataResult | None:
        if not data:
            return None
        title = data.get("title_english") or data.get("title") or "Unknown"
        genres = [g["name"] for g in (data.get("genres") or []) if isinstance(g, dict)]
        themes = [g["name"] for g in (data.get("themes") or []) if isinstance(g, dict)]
        cover_url = None
        images = data.get("images") or {}
        for fmt in ("jpg", "webp"):
            block = images.get(fmt) or {}
            cover_url = block.get("large_image_url") or block.get("image_url") or cover_url
            if cover_url:
                break
        return MetadataResult(
            title=title,
            description=data.get("synopsis"),
            status=MAL_STATUS_MAP.get(data.get("status", ""), "ongoing"),
            cover_url=cover_url,
            genres=genres + themes,
            url=data.get("url", ""),
        )

    async def lookup_mal(self, title: str) -> MetadataResult | None:
        resp = await _get_with_retry(
            self._client, f"{JIKAN_URL}/manga", params={"q": title, "limit": 5}
        )
        resp.raise_for_status()
        body = resp.json()
        results = body.get("data") or []
        if not results:
            return None
        results.sort(key=lambda r: r.get("members") or 0, reverse=True)
        return self._parse_mal_data(results[0])

    async def _scrape_mal_page(self, manga_id: int) -> MetadataResult | None:
        """Fallback: scrape the public myanimelist.net page when Jikan is down."""
        url = f"https://myanimelist.net/manga/{manga_id}"
        try:
            resp = await _get_with_retry(
                self._client, url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            if resp.status_code != 200:
                return None
            html = resp.text
            doc = HTMLParser(html)

            # Title — MAL bundles "Edit" link + form text inside the h1 element
            # so we take only the first non-empty line and trim aggressively.
            t_el = doc.css_first("h1.title-name strong, h1[itemprop='name'] strong, h1.title-name, h1[itemprop='name'], h1.h1")
            raw_title = (t_el.text() or "").strip() if t_el else ""
            title = raw_title.split("\n")[0].strip() or f"MAL #{manga_id}"

            # Synopsis
            desc_el = doc.css_first("[itemprop='description'], .js-scrollfix-bottom-rel p[itemprop='description']")
            description = (desc_el.text() or "").strip() if desc_el else None

            # Cover image
            cover = None
            img = doc.css_first("img[itemprop='image'], img.lazyloaded")
            if img:
                cover = (
                    img.attributes.get("data-src")
                    or img.attributes.get("src")
                )

            # Status — sidebar has "Status: Finished" lines
            status_raw = ""
            for span in doc.css("div.spaceit_pad span.dark_text"):
                if (span.text() or "").strip().lower().startswith("status"):
                    parent = span.parent
                    if parent:
                        full = (parent.text() or "").strip()
                        status_raw = full.split(":", 1)[-1].strip().lower()
                        break

            # Genres
            genres: list[str] = []
            for a in doc.css("span[itemprop='genre'], a[href*='/genre/']"):
                t = (a.text() or "").strip()
                if t and t not in genres:
                    genres.append(t)

            return MetadataResult(
                title=title,
                description=description,
                status=MAL_STATUS_MAP.get(status_raw.title(), "ongoing"),
                cover_url=cover,
                genres=genres[:15],
                url=url,
            )
        except Exception:
            return None

    # ---- Anime-Planet (HTML scrape) ----

    async def _parse_animeplanet_page(self, slug: str) -> MetadataResult | None:
        url = f"{AP_BASE}/manga/{slug}"
        resp = await _get_with_retry(self._client, url, headers=AP_HEADERS)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        doc = HTMLParser(resp.text)

        # Title
        title_el = doc.css_first("h1[itemprop='name'], h1.long")
        title = (title_el.text() or "").strip() if title_el else slug

        # Description
        desc_el = doc.css_first("[itemprop='description'], .entrySynopsis p")
        description = (desc_el.text() or "").strip() if desc_el else None

        # Cover
        cover = None
        cover_el = doc.css_first("img.screenshots, .screenshots img")
        if cover_el:
            src = cover_el.attributes.get("src") or cover_el.attributes.get("data-src")
            if src:
                cover = urljoin(AP_BASE, src)

        # Status from sidebar metadata
        status_text = ""
        for el in doc.css(".pure-1.md-1-5"):
            t = (el.text() or "").lower()
            if "vol" in t or "ch" in t or "publish" in t or "ongoing" in t or "finished" in t:
                status_text += " " + t
        # Fallback: check the section heading
        meta_section = doc.css_first(".sidebarBlock, .pure-g")
        if meta_section:
            status_text += " " + (meta_section.text() or "")

        # Genres / tags
        genres: list[str] = []
        for a in doc.css(".tags a, ul.tags a"):
            t = (a.text() or "").strip()
            if t and t not in genres:
                genres.append(t)
        # Limit to a sensible number
        genres = genres[:15]

        return MetadataResult(
            title=title,
            description=description,
            status=_ap_status(status_text),
            cover_url=cover,
            genres=genres,
            url=url,
        )

    async def lookup_animeplanet(self, title: str) -> MetadataResult | None:
        # Anime-Planet's site search redirects when there's an exact match.
        search_url = f"{AP_BASE}/manga/all?name={quote_plus(title)}"
        resp = await _get_with_retry(self._client, search_url, headers=AP_HEADERS)
        if resp.status_code >= 400:
            return None
        # If they redirected straight to a series page, parse it.
        if "/manga/" in str(resp.url) and "/manga/all" not in str(resp.url):
            slug = str(resp.url).rstrip("/").rsplit("/", 1)[-1]
            return await self._parse_animeplanet_page(slug)

        doc = HTMLParser(resp.text)
        first = doc.css_first("ul.cardDeck a.tooltip, .cardList a.tooltip, .cardList a")
        if not first:
            return None
        href = first.attributes.get("href") or ""
        m = AP_URL_PATTERN.search(urljoin(AP_BASE, href))
        if not m:
            return None
        return await self._parse_animeplanet_page(m.group(1))

    # ---- URL dispatch ----

    async def fetch_from_url(self, url: str) -> MetadataResult | None:
        m = ANILIST_URL_PATTERN.search(url)
        if m:
            kind = m.group(1)  # "manga" or "anime"
            anilist_id = int(m.group(2))
            slug = (m.group(3) or "").replace("-", " ").strip()

            if kind == "manga":
                resp = await self._client.post(
                    ANILIST_URL,
                    json={"query": ID_QUERY, "variables": {"id": anilist_id}},
                )
                resp.raise_for_status()
                media = resp.json().get("data", {}).get("Media")
                if media:
                    return self._parse_anilist_media(media)
                # If the manga ID returned nothing, fall through to title search

            # Anime URL (or manga ID miss) — search for the manga by title.
            # Use the URL's slug as a search hint when available.
            search_term = slug or ""
            if search_term:
                try:
                    r = await self.lookup_anilist(search_term)
                    if r:
                        return r
                except Exception:
                    pass
            # Last-ditch: don't return manga metadata for an anime that has
            # no manga adaptation
            return None

        m = MAL_URL_PATTERN.search(url)
        if m:
            manga_id = int(m.group(1))
            # Try Jikan first (clean JSON). If it's down, fall back to scraping
            # myanimelist.net directly so the user's manual URL still works.
            try:
                resp = await _get_with_retry(self._client, f"{JIKAN_URL}/manga/{manga_id}")
                resp.raise_for_status()
                data = resp.json().get("data")
                if data:
                    return self._parse_mal_data(data)
            except Exception:
                pass
            return await self._scrape_mal_page(manga_id)

        m = AP_URL_PATTERN.search(url)
        if m:
            return await self._parse_animeplanet_page(m.group(1))

        return None

    async def lookup_any(self, title: str) -> MetadataResult | None:
        """Try AniList → MyAnimeList → Anime-Planet, return first hit whose
        title actually resembles the query.

        Short / generic titles ("Out", "Smile!", "Tower") match unrelated
        series in metadata APIs, so we score each candidate against the query
        and reject poor matches to avoid mismatched covers/metadata.
        """
        target = _normalize_title(title)
        if not target:
            return None
        # Single-word titles need a stricter threshold.
        threshold = 0.85 if len(target.split()) <= 1 else 0.6

        for fn in (self.lookup_anilist, self.lookup_mal, self.lookup_animeplanet):
            try:
                r = await fn(title)
            except Exception:
                continue
            if not r:
                continue
            score = _title_similarity(target, _normalize_title(r.title))
            if score >= threshold:
                return r
        return None
