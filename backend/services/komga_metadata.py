"""Komga-compatible metadata writers.

Komga reads two kinds of local metadata:
- `series.json` placed in the series folder (series-level)
- `ComicInfo.xml` embedded inside each CBZ (chapter-level)

These functions write both based on the AniList-style MetadataResult.
"""
import json
import os
import re
import zipfile
from xml.sax.saxutils import escape

import httpx

from services.metadata_service import MetadataResult

COVER_FILENAMES = ("cover.jpg", "cover.png", "cover.jpeg", "cover.webp")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _ext_for_image(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


async def download_cover(
    folder: str, cover_url: str | None, force: bool = False
) -> str | None:
    """Fetch cover_url and save as cover.{ext} in series folder.

    Returns the path written, or None on failure / when a cover already exists
    (unless force=True, which replaces any existing cover.*). When force=True
    but the download fails, the existing cover is restored — we never end up
    worse off than when we started.
    """
    if not cover_url:
        return None
    os.makedirs(folder, exist_ok=True)

    # Track existing covers so we can restore them on failure.
    existing: list[tuple[str, bytes]] = []
    if force:
        for name in COVER_FILENAMES:
            p = os.path.join(folder, name)
            if os.path.exists(p):
                try:
                    with open(p, "rb") as fh:
                        existing.append((p, fh.read()))
                except OSError:
                    pass
    else:
        for name in COVER_FILENAMES:
            if os.path.exists(os.path.join(folder, name)):
                return None

    # Pick a Referer based on URL host, with overrides for known CDNs.
    from urllib.parse import urlparse
    host = (urlparse(cover_url).hostname or "").lower()
    REFERER_OVERRIDES = {
        "readdetectiveconan.com": "https://mangapill.com/",
        "compsci88.com": "https://weebcentral.com/",
        "planeptune.us": "https://weebcentral.com/",
        "cdn.asurascans.com": "https://asurascans.com/",
        "asurascans.com": "https://asurascans.com/",
        "mangakatana.com": "https://mangakatana.com/",
    }
    referer = None
    for needle, ref in REFERER_OVERRIDES.items():
        if host == needle or host.endswith("." + needle):
            referer = ref
            break
    if not referer:
        referer = f"https://{host}/" if host else ""

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as c:
            r = await c.get(cover_url, headers={
                "User-Agent": UA,
                "Referer": referer,
                "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
            })
            r.raise_for_status()
            data = r.content
            if not data or len(data) < 500:
                raise ValueError("empty/tiny response")
            ext = _ext_for_image(data)
            # Now safe to delete old cover(s) before writing the new one
            for name in COVER_FILENAMES:
                p = os.path.join(folder, name)
                if os.path.exists(p):
                    try: os.remove(p)
                    except OSError: pass
            out_path = os.path.join(folder, f"cover.{ext}")
            with open(out_path, "wb") as fh:
                fh.write(data)
            return out_path
    except Exception:
        # Restore previous covers if download failed
        for path, data in existing:
            if not os.path.exists(path):
                try:
                    with open(path, "wb") as fh:
                        fh.write(data)
                except OSError:
                    pass
        return None


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    # AniList descriptions contain HTML tags + line breaks; convert to plain text
    cleaned = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return cleaned.strip()


def _komga_status(status: str) -> str:
    # Komga accepts: ENDED, ONGOING, ABANDONED, HIATUS
    s = (status or "").lower()
    if s == "complete":
        return "ENDED"
    if s == "ongoing":
        return "ONGOING"
    return "ONGOING"


def _mylar_status(status: str) -> str:
    # Mylar3 uses "Continuing" / "Ended"
    s = (status or "").lower()
    if s == "complete":
        return "Ended"
    return "Continuing"


def write_series_json(series_folder: str, meta: MetadataResult) -> str:
    """Write a series.json (Mylar3 format) that Komga reads natively.

    Returns the path written.
    """
    os.makedirs(series_folder, exist_ok=True)
    summary = _strip_html(meta.description)
    payload = {
        "version": "1.0.2",
        "metadata": {
            "type": "comicSeries",
            "name": meta.title,
            "publisher": "",
            "imprint": None,
            "comicid": 0,
            "year": 0,
            "description_text": summary,
            "description_formatted": summary,
            "volume": None,
            "booktype": "Print",
            "collects": [],
            "ComicImage": meta.cover_url or "",
            "total_issues": 0,
            "publication_run": "",
            "status": _mylar_status(meta.status),
            # Komga also reads these extras when present
            "genre": ", ".join(meta.genres or []),
        },
    }
    path = os.path.join(series_folder, "series.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def make_comicinfo_xml(
    *,
    series_title: str,
    chapter_number: float,
    chapter_title: str | None,
    summary: str | None = None,
    genres: list[str] | None = None,
    year: int | None = None,
    publisher: str | None = None,
    status: str | None = None,
) -> str:
    """Build a ComicInfo.xml string for embedding inside a CBZ."""
    num_str = (
        str(int(chapter_number))
        if chapter_number == int(chapter_number)
        else str(chapter_number)
    )
    parts: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>', "<ComicInfo>"]
    parts.append(f"  <Series>{escape(series_title)}</Series>")
    parts.append(f"  <Number>{escape(num_str)}</Number>")
    if chapter_title:
        parts.append(f"  <Title>{escape(chapter_title)}</Title>")
    summary_clean = _strip_html(summary) if summary else ""
    if summary_clean:
        parts.append(f"  <Summary>{escape(summary_clean)}</Summary>")
    if genres:
        parts.append(f"  <Genre>{escape(','.join(genres))}</Genre>")
    if year is not None:
        parts.append(f"  <Year>{year}</Year>")
    if publisher:
        parts.append(f"  <Publisher>{escape(publisher)}</Publisher>")
    parts.append("</ComicInfo>")
    return "\n".join(parts)


def inject_comicinfo_into_cbz(cbz_path: str, comicinfo_xml: str) -> None:
    """Add or replace ComicInfo.xml inside an existing CBZ.

    Komga reads this for per-chapter metadata.
    """
    if not os.path.exists(cbz_path):
        return
    tmp_path = cbz_path + ".tmp"
    with zipfile.ZipFile(cbz_path, "r") as src, zipfile.ZipFile(
        tmp_path, "w", zipfile.ZIP_STORED
    ) as dst:
        for item in src.namelist():
            if item.lower() == "comicinfo.xml":
                continue
            dst.writestr(item, src.read(item))
        dst.writestr("ComicInfo.xml", comicinfo_xml)
    os.replace(tmp_path, cbz_path)
