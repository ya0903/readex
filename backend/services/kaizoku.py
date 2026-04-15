"""Optional Kaizoku integration.

Exposes helpers to look up and delete series in a co-located Kaizoku instance
via its tRPC API (no auth required since it's intended for homelab use).
"""
import re
from typing import Any

import httpx

from config import settings


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def is_enabled() -> bool:
    return bool((settings.kaizoku_url or "").strip())


async def list_kaizoku_manga() -> list[dict[str, Any]]:
    """Return Kaizoku's full manga list (id, title, ...). Empty list on error."""
    if not is_enabled():
        return []
    url = settings.kaizoku_url.rstrip("/") + "/api/trpc/manga.query"
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            data = r.json()
            # tRPC v9 response shape: {result: {data: {json: [...]}}}
            payload = data.get("result", {}).get("data", {})
            return payload.get("json") or payload or []
    except Exception:
        return []


async def find_in_kaizoku(title: str) -> int | None:
    """Find a manga in Kaizoku by fuzzy title match. Returns its id or None."""
    target = _norm(title)
    if not target:
        return None
    for m in await list_kaizoku_manga():
        t = _norm(m.get("title", ""))
        if t and (t == target or target in t or t in target):
            return m.get("id")
    return None


async def remove_from_kaizoku(manga_id: int, remove_files: bool = False) -> bool:
    """Call Kaizoku's `manga.remove` mutation. Returns True on success."""
    if not is_enabled() or not manga_id:
        return False
    url = settings.kaizoku_url.rstrip("/") + "/api/trpc/manga.remove"
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(
                url,
                json={
                    "json": {
                        "id": manga_id,
                        "shouldRemoveFiles": bool(remove_files),
                    }
                },
            )
            return r.status_code < 400
    except Exception:
        return False


async def remove_by_title(title: str) -> dict:
    """Convenience: look up by title, remove if found.

    Returns {"matched": bool, "id": int|None, "removed": bool}
    """
    if not is_enabled():
        return {"matched": False, "id": None, "removed": False}
    mid = await find_in_kaizoku(title)
    if mid is None:
        return {"matched": False, "id": None, "removed": False}
    ok = await remove_from_kaizoku(mid, remove_files=False)
    return {"matched": True, "id": mid, "removed": ok}
