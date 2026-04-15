"""Image proxy for cover URLs that require a Referer header.

Many manga sites (mangapill, asurascans, weebcentral, etc.) host cover art on
CDNs that block direct access without the proper Referer. Browsers can't set
a custom Referer for `<img>` tags, so we proxy through the backend.

Usage from the frontend: `/api/proxy/image?url=<encoded image url>`
"""
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

# Map a hostname (or any host suffix match) to the Referer URL the CDN expects.
REFERER_BY_HOST = {
    "readdetectiveconan.com": "https://mangapill.com/",
    "mangapill.com": "https://mangapill.com/",
    "asuracomic.net": "https://asuracomic.net/",
    "asurascans.com": "https://asurascans.com/",
    "weebcentral.com": "https://weebcentral.com/",
    "compsci88.com": "https://weebcentral.com/",
    "planeptune.us": "https://weebcentral.com/",
    "mangakatana.com": "https://mangakatana.com/",
    "aquareader.net": "https://aquareader.net/",
    "anime-planet.com": "https://www.anime-planet.com/",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

ALLOWED_SCHEMES = {"http", "https"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB cap on proxied responses


def _referer_for(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    for needle, ref in REFERER_BY_HOST.items():
        if host == needle or host.endswith("." + needle):
            return ref
    return None


@router.get("/image")
async def proxy_image(request: Request, url: str = Query(..., min_length=10)):
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")

    referer = _referer_for(url) or f"{parsed.scheme}://{parsed.hostname}/"
    headers = {
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/png,image/*,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as c:
            r = await c.get(url, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail="Upstream returned error")

    body = r.content
    if len(body) > MAX_BYTES:
        body = body[:MAX_BYTES]

    media_type = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return Response(
        content=body,
        media_type=media_type,
        headers={
            # Cache for an hour so repeat browsing doesn't re-fetch covers
            "Cache-Control": "public, max-age=3600",
        },
    )
