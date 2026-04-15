import asyncio

from sources.base import SourceAdapter, SearchResult


class SourceRegistry:
    def __init__(self):
        self._sources: dict[str, SourceAdapter] = {}

    def register(self, source: SourceAdapter):
        self._sources[source.name] = source

    def get(self, name: str) -> SourceAdapter | None:
        return self._sources.get(name)

    def list_sources(self) -> list[str]:
        return list(self._sources.keys())

    async def search_all(self, query: str) -> list[SearchResult]:
        tasks = [source.search(query) for source in self._sources.values()]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for r in results_nested:
            if isinstance(r, list):
                results.extend(r)
        return results
