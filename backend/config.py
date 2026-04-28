from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/readex.db"
    # Default library folder. Used as a fallback when a content-type-specific
    # path isn't set (e.g. when a user only mounts one library volume).
    library_path: str = "/library"
    # Optional per-content-type library paths. Empty string = fall back to library_path.
    # Mount these inside the container, e.g.:
    #   /library/manga, /library/manhwa, /library/comics
    manga_path: str = ""
    manhwa_path: str = ""
    comic_path: str = ""
    # Light novel library root. Unlike the others this is also editable from
    # the Settings UI (persisted to data/settings.json) since light novels
    # were added later and most users won't have an env var set for them.
    lightnovel_path: str = ""
    concurrent_downloads: int = 3
    metadata_auto_lookup: bool = True
    default_schedule_interval: int = 21600  # 6 hours in seconds
    # Optional FlareSolverr endpoint for bypassing Cloudflare / JS-rendered sites.
    # Empty string disables it. Example: "http://flaresolverr:8191/v1"
    flaresolverr_url: str = ""
    # Optional Kaizoku base URL — when set, importing into Readex will also
    # remove the matching series from Kaizoku (DB only, files preserved).
    # Example: "http://kaizoku:3000" (Docker network) or "http://192.168.1.2:2100"
    kaizoku_url: str = ""
    # Optional Komga base URL + API key — when set, Readex will trigger a
    # library re-scan after writing metadata so summaries/covers show up
    # without manual intervention.
    # Generate an API key in Komga → Account Settings → API Keys.
    komga_url: str = ""
    komga_api_key: str = ""

    model_config = {"env_prefix": "READEX_"}

    def library_path_for(self, content_type: str) -> str:
        """Return the library root for a given content_type, falling back to
        `library_path` when no specific override is set."""
        ct = (content_type or "").lower()
        if ct == "manga" and self.manga_path:
            return self.manga_path
        if ct == "manhwa" and self.manhwa_path:
            return self.manhwa_path
        if ct == "comic" and self.comic_path:
            return self.comic_path
        if ct == "lightnovel" and self.lightnovel_path:
            return self.lightnovel_path
        return self.library_path


settings = Settings()
