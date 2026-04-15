"""Helper for routing requests through FlareSolverr.

FlareSolverr is a self-hosted proxy that runs a real browser to bypass
Cloudflare anti-bot challenges and render JavaScript. We use it for sources
like AquaReader (Cloudflare-protected) and AsuraScans (Next.js client-rendered).

Configure with `READEX_FLARESOLVERR_URL=http://flaresolverr:8191/v1` env var.
If unset, callers should fall back to plain httpx.
"""
import httpx

from config import settings


async def flaresolverr_get(url: str, max_timeout_ms: int = 60000) -> str | None:
    """GET a URL via FlareSolverr; returns the rendered HTML, or None if unavailable.

    Returns None on any error so callers can fall back to a direct fetch.
    """
    endpoint = (settings.flaresolverr_url or "").strip()
    if not endpoint:
        return None
    try:
        async with httpx.AsyncClient(timeout=max(30.0, max_timeout_ms / 1000)) as c:
            r = await c.post(
                endpoint,
                json={
                    "cmd": "request.get",
                    "url": url,
                    "maxTimeout": max_timeout_ms,
                },
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("status") != "ok":
                return None
            return (data.get("solution") or {}).get("response")
    except Exception:
        return None


def is_enabled() -> bool:
    return bool((settings.flaresolverr_url or "").strip())
