"""Optional Komga integration — triggers library re-scans so that newly-written
series.json / cover files / ComicInfo.xml updates show up in Komga right away.
"""
import asyncio
import logging
from typing import Any

import httpx

from config import settings

log = logging.getLogger("readex.komga")


def is_enabled() -> bool:
    return bool(
        (settings.komga_url or "").strip()
        and (settings.komga_api_key or "").strip()
    )


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.komga_url.rstrip("/"),
        headers={"X-API-Key": settings.komga_api_key},
        timeout=15.0,
    )


async def list_libraries() -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    try:
        async with _client() as c:
            r = await c.get("/api/v1/libraries")
            if r.status_code == 200:
                return r.json() or []
    except Exception:
        pass
    return []


# Throttle how often we trigger scans (Komga scans can be heavy).
_last_scan: dict[str, float] = {}
_SCAN_DEBOUNCE_SECONDS = 30


async def trigger_scan_for_path(folder: str) -> bool:
    """Trigger a scan of whatever library contains `folder`.

    Returns True if a scan was kicked off, False if Komga is disabled, the
    folder isn't in any Komga library, or the request failed.
    """
    if not is_enabled():
        return False
    libs = await list_libraries()
    if not libs:
        return False

    target_lib = None
    for lib in libs:
        roots = lib.get("root", "") or lib.get("roots", [])
        if isinstance(roots, str):
            roots = [roots]
        # The Readex container sees /library, but Komga sees the host path.
        # Match by suffix — fold both to lowercase for case-insensitive volumes.
        for root in roots:
            r = (root or "").rstrip("/").lower()
            f = folder.rstrip("/").lower()
            if r and (f.startswith(r) or r.endswith(f.split("/")[-1])):
                target_lib = lib
                break
        if target_lib:
            break

    # If we couldn't pin to one library, scan all libraries (cheap if nothing changed).
    targets = [target_lib] if target_lib else libs
    import time
    now = time.time()
    triggered = False
    try:
        async with _client() as c:
            for lib in targets:
                lid = lib.get("id")
                if not lid:
                    continue
                if now - _last_scan.get(lid, 0) < _SCAN_DEBOUNCE_SECONDS:
                    continue
                _last_scan[lid] = now
                r = await c.post(f"/api/v1/libraries/{lid}/scan")
                if r.status_code in (202, 204):
                    triggered = True
                    log.info(f"triggered Komga scan on library {lid}")
    except Exception as e:
        log.warning(f"Komga scan failed: {e}")
    return triggered


def trigger_scan_in_background(folder: str) -> None:
    """Fire-and-forget scan trigger."""
    if not is_enabled():
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(trigger_scan_for_path(folder))
    except RuntimeError:
        # No running loop (called from sync context) — spawn a thread
        import threading
        threading.Thread(
            target=lambda: asyncio.run(trigger_scan_for_path(folder)),
            daemon=True,
        ).start()
