<div align="center">

<img src="frontend/public/readex.png" alt="Readex" width="120" />

# Readex

**A self-hosted manga, manhwa, and comics downloader for homelab servers.**

Reliable scraping, library-aware duplicate detection, per-series scheduling,
and metadata that actually shows up in Komga.

</div>

---

## Why this exists

Existing self-hosted manga downloaders had real problems in production:

- Rigid title matching against AniList — if the source's title didn't match
  exactly, downloads were blocked
- Scheduled "check for new chapters" rarely fired
- No awareness of what was already on disk → duplicate downloads everywhere
- No clean way to fold in chapters released after a "completed" download
- Scrapers broke and stayed broken for popular sites

Readex addresses each of these. It's intentionally opinionated for a homelab
setup paired with [Komga](https://komga.org/) (or Kavita) as the reader.

## Features

- **8 source adapters**: MangaDex (official API), AsuraScans, WeebCentral,
  MangaPill, MangaKatana, GetComics, ReadComicOnline (plus a base class to
  add more — one Python file per source)
- **Library-aware**: scans your download folder on startup and matches
  existing CBZ files, no duplicates
- **Per-series scheduling**: pick an interval per series (or "never" for
  completed ones)
- **Metadata enrichment from AniList / MyAnimeList / Anime-Planet** — never
  blocks downloads, with manual URL override per series
- **Komga integration**:
  - Writes Mylar3 `series.json` + `cover.jpg` so Komga shows summaries,
    genres, and cover art automatically
  - Triggers Komga library rescans via API after metadata writes
- **FlareSolverr support**: bypass Cloudflare for sites that need it
- **Bulk operations**: select multiple series in the library to retry failed
  downloads, sync metadata, or delete
- **Optional Kaizoku migration**: when importing folders, Readex can
  auto-remove the matching series from a running Kaizoku instance (DB only,
  files preserved) — set `READEX_KAIZOKU_URL` to enable
- **Per-content-type library paths**: route manga / manhwa / comics to
  separate folders (so each can be its own Komga library)
- **Resilient downloads**: page-by-page progress, retry queue, recovery
  from container restarts mid-download
- **Atomic CBZ writes** with embedded `ComicInfo.xml` for chapter metadata
- **Reader-agnostic**: outputs CBZ to a folder, works with Komga, Kavita, or
  anything that watches a folder

## Screenshots

The UI is a dark React SPA — Library grid, Search across all sources, Queue
with per-page progress, Series detail with chapter management, plus an
Import flow for existing folders.

## Quick Start

### Requirements

- A Linux server with Docker + Docker Compose
- A folder you want manga downloaded into (typically the same one your reader
  watches)

### Setup

```bash
git clone https://github.com/ya0903/readex.git
cd readex
```

Edit `docker-compose.yml`:

```yaml
volumes:
  - ./data:/app/data
  - /your/manga/library:/library  # <-- change this
```

Then:

```bash
docker compose up -d --build
```

The first build takes a few minutes (it installs Playwright + Chromium for
JS-heavy source adapters).

Open `http://your-server:3150` in a browser.

### Importing your existing library

If you already have manga folders on disk, open the **Import** tab in the UI.
It scans your library root, lists everything that isn't already tracked, and
bulk-imports with metadata fetch.

## Configuration

All settings are environment variables prefixed with `READEX_`. Set them in
`docker-compose.yml`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `READEX_LIBRARY_PATH` | `/library` | Default download folder (used when a content-type-specific path isn't set) |
| `READEX_MANGA_PATH` | *(falls back to LIBRARY_PATH)* | Where manga downloads go |
| `READEX_MANHWA_PATH` | *(falls back to LIBRARY_PATH)* | Where manhwa downloads go |
| `READEX_COMIC_PATH` | *(falls back to LIBRARY_PATH)* | Where comics downloads go |
| `READEX_DATABASE_URL` | `sqlite:///./data/readex.db` | SQLite DB location |
| `READEX_CONCURRENT_DOWNLOADS` | `3` | Max simultaneous chapter downloads |
| `READEX_METADATA_AUTO_LOOKUP` | `true` | Auto-fetch metadata on add |
| `READEX_DEFAULT_SCHEDULE_INTERVAL` | `21600` *(6h)* | Default check interval (seconds) |
| `READEX_FLARESOLVERR_URL` | *(empty)* | FlareSolverr endpoint, e.g. `http://flaresolverr:8191/v1` |
| `READEX_KOMGA_URL` | *(empty)* | Komga base URL for auto-rescan, e.g. `http://komga:25600` |
| `READEX_KOMGA_API_KEY` | *(empty)* | Komga API key — generate in Komga → Account Settings → API Keys |
| `READEX_KAIZOKU_URL` | *(empty)* | Optional. When set, importing into Readex auto-removes the matching series from Kaizoku (DB only, files kept) |

The Komga URL + API key can also be set/changed at runtime through the **Settings** page in the UI (persisted to `data/settings.json`).

### Folder structure on disk

Readex outputs CBZ files in a flat structure that any reader can index:

```
/library/
├── One Piece/
│   ├── Chapter 1100.cbz
│   ├── Chapter 1101.cbz
│   ├── series.json        ← Mylar3-format metadata for Komga
│   └── cover.jpg          ← Cover art from AniList / MAL / Anime-Planet
├── Solo Leveling/
│   └── Chapter 200.cbz
└── Batman (2016)/
    ├── Issue 001.cbz
    └── Issue 002.cbz
```

- Manga / manhwa get `Chapter N.cbz` naming
- Comics get `Issue NNN.cbz` naming (zero-padded)
- Each CBZ has a `ComicInfo.xml` inside with chapter metadata Komga reads

## Working with Komga

Readex is designed to slot into a Komga setup. Mount the same folder as
both your `READEX_LIBRARY_PATH` and Komga's library root. Then:

1. Download something in Readex
2. Set up the API key for auto-rescan (optional but recommended)
3. Komga shows the new chapter, summary, genres, and cover automatically

If you don't want auto-rescan, enable Komga's **Filesystem Watcher** on the
library, or trigger scans manually after downloads.

## Source status

| Source | Status | Notes |
|--------|--------|-------|
| MangaDex | Stable | Official API, no scraping |
| AsuraScans | Stable | Requires FlareSolverr (Cloudflare) |
| WeebCentral | Stable | |
| MangaPill | Stable | |
| MangaKatana | Stable | |
| GetComics | Working | Western comics, downloads CBR/ZIP archives |
| ReadComicOnline | Scaffold | Image viewer needs JS — works partially |

Sites that proved too JS-heavy or actively bot-blocked were not implemented:
AquaReader, DemonicScans, atsu.moe, mangaball.net.

## Adding a new source

Drop a Python file into `backend/sources/` implementing `SourceAdapter`:

```python
from sources.base import ChapterInfo, SearchResult, SeriesInfo, SourceAdapter

class MySource(SourceAdapter):
    name = "mysource"
    base_url = "https://example.com"
    content_type = "manga"
    supports_url = True

    async def search(self, query: str) -> list[SearchResult]: ...
    async def get_chapters(self, series_id: str) -> list[ChapterInfo]: ...
    async def download_chapter(self, chapter: ChapterInfo,
                               progress_cb=None) -> list[bytes]: ...
    async def parse_url(self, url: str) -> SeriesInfo | None: ...
    async def check_updates(self, series_id: str) -> list[ChapterInfo]: ...
```

Register it in `backend/main.py`'s lifespan handler. Restart the container.

## Tech stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (SQLite), APScheduler, httpx,
  selectolax, Playwright (for JS-rendered sites)
- **Frontend**: React 18, TypeScript, Vite (single-page app, dark theme)
- **Container**: Multi-stage Docker build (Node for frontend, Python for backend)

## Development

Backend:

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --port 3100 --reload
python -m pytest tests/  # 42 tests
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # Vite dev server on port 5173, proxies /api to 3100
```

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- [Komga](https://komga.org/) — the reader Readex is built around
- [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) — for handling
  Cloudflare on JS-rendered sources
