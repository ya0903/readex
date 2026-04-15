from fastapi import APIRouter, HTTPException, Request

from schemas import SearchRequest, SearchResultOut, UrlParseRequest

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=list[SearchResultOut])
async def search(data: SearchRequest, request: Request):
    registry = request.app.state.source_registry
    if data.sources:
        results = []
        for source_name in data.sources:
            source = registry.get(source_name)
            if source:
                try:
                    results.extend(await source.search(data.query))
                except Exception:
                    continue
    else:
        results = await registry.search_all(data.query)
    return [
        SearchResultOut(
            source_name=r.source_name,
            source_id=r.source_id,
            title=r.title,
            cover_url=r.cover_url,
            content_type=r.content_type,
            chapter_count=r.chapter_count,
            status=r.status,
            url=r.url,
        )
        for r in results
    ]


@router.post("/url")
async def parse_url(data: UrlParseRequest, request: Request):
    registry = request.app.state.source_registry
    for source_name in registry.list_sources():
        source = registry.get(source_name)
        if source:
            try:
                info = await source.parse_url(data.url)
            except Exception:
                continue
            if info:
                return {
                    "source_name": info.source_name,
                    "source_id": info.source_id,
                    "title": info.title,
                    "cover_url": info.cover_url,
                    "content_type": info.content_type,
                    "url": info.url,
                }
    return {"error": "Could not parse URL from any source"}


@router.get("/preview")
async def preview_chapters(
    source_name: str, source_id: str, request: Request
):
    """Return the chapter list from a source without creating a series.

    Used by the Add flow so the user can see what they're about to add.
    """
    registry = request.app.state.source_registry
    source = registry.get(source_name)
    if source is None:
        raise HTTPException(
            status_code=404, detail=f"Source '{source_name}' not found"
        )
    try:
        chapters = await source.get_chapters(source_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Source error: {e}")
    return [
        {
            "source_chapter_id": ch.source_chapter_id,
            "chapter_number": ch.chapter_number,
            "title": ch.title,
            "url": ch.url,
        }
        for ch in chapters
    ]
