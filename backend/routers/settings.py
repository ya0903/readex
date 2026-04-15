import json
import os

from fastapi import APIRouter, Request
from config import settings
from schemas import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Path to a small overrides file that persists user-set settings (currently
# just the Komga URL + API key). Sits next to the SQLite DB.
_OVERRIDES_PATH = "/app/data/settings.json"


def _load_overrides() -> dict:
    try:
        with open(_OVERRIDES_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_overrides(data: dict) -> None:
    os.makedirs(os.path.dirname(_OVERRIDES_PATH), exist_ok=True)
    with open(_OVERRIDES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def apply_overrides_on_startup() -> None:
    """Re-apply persisted user overrides on top of env-var defaults."""
    for k, v in _load_overrides().items():
        if hasattr(settings, k):
            object.__setattr__(settings, k, v)


def _to_out(registry) -> SettingsOut:
    return SettingsOut(
        library_path=settings.library_path,
        manga_path=settings.manga_path,
        manhwa_path=settings.manhwa_path,
        comic_path=settings.comic_path,
        concurrent_downloads=settings.concurrent_downloads,
        metadata_auto_lookup=settings.metadata_auto_lookup,
        default_schedule_interval=settings.default_schedule_interval,
        sources=registry.list_sources(),
        komga_url=settings.komga_url,
        komga_api_key_set=bool((settings.komga_api_key or "").strip()),
    )


@router.get("", response_model=SettingsOut)
def get_settings(request: Request):
    return _to_out(request.app.state.source_registry)


@router.patch("", response_model=SettingsOut)
def update_settings(data: SettingsUpdate, request: Request):
    overrides = _load_overrides()
    for field, value in data.model_dump(exclude_unset=True).items():
        if hasattr(settings, field):
            object.__setattr__(settings, field, value)
            # Persist Komga settings so they survive restart
            if field in ("komga_url", "komga_api_key"):
                overrides[field] = value
    _save_overrides(overrides)
    return _to_out(request.app.state.source_registry)
