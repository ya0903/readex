from datetime import datetime

from pydantic import BaseModel


# --- Series ---

class SeriesCreate(BaseModel):
    title: str
    folder_name: str
    source_name: str
    source_id: str
    content_type: str  # manga, manhwa, comic, lightnovel
    status: str  # ongoing, complete
    metadata_url: str | None = None
    cover_url: str | None = None
    schedule_interval: int | None = None  # seconds, None = no schedule


class SeriesUpdate(BaseModel):
    title: str | None = None
    folder_name: str | None = None
    status: str | None = None
    metadata_url: str | None = None
    cover_url: str | None = None


class ChapterOut(BaseModel):
    id: int
    series_id: int
    chapter_number: float
    title: str | None
    status: str
    file_path: str | None
    downloaded_at: datetime | None

    model_config = {"from_attributes": True}


class ScheduleOut(BaseModel):
    id: int
    series_id: int
    interval_seconds: int
    check_time: str | None = None
    check_day_of_week: int | None = None
    last_checked_at: datetime | None
    next_check_at: datetime | None
    enabled: bool

    model_config = {"from_attributes": True}


class SeriesOut(BaseModel):
    id: int
    title: str
    folder_name: str
    source_name: str
    source_id: str
    content_type: str
    status: str
    metadata_url: str | None
    metadata_synced_at: datetime | None = None
    cover_url: str | None
    created_at: datetime
    updated_at: datetime
    chapter_count: int = 0
    downloaded_count: int = 0

    model_config = {"from_attributes": True}


class SeriesDetailOut(SeriesOut):
    chapters: list[ChapterOut] = []
    schedule: ScheduleOut | None = None


# --- Search ---

class SearchRequest(BaseModel):
    query: str
    sources: list[str] | None = None  # None = all sources


class SearchResultOut(BaseModel):
    source_name: str
    source_id: str
    title: str
    cover_url: str | None
    content_type: str
    chapter_count: int | None
    status: str | None
    url: str


class UrlParseRequest(BaseModel):
    url: str


# --- Downloads ---

class DownloadRequest(BaseModel):
    series_id: int
    chapter_ids: list[int] | None = None  # None = all available


class QueueItemOut(BaseModel):
    id: int
    chapter_id: int
    series_title: str
    chapter_number: float
    priority: int
    status: str
    error_message: str | None
    retries: int
    progress_current: int = 0
    progress_total: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Schedules ---

class ScheduleCreate(BaseModel):
    series_id: int
    interval_seconds: int
    check_time: str | None = None
    check_day_of_week: int | None = None
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    interval_seconds: int | None = None
    check_time: str | None = None
    check_day_of_week: int | None = None
    enabled: bool | None = None


# --- Settings ---

class SettingsOut(BaseModel):
    library_path: str
    manga_path: str = ""
    manhwa_path: str = ""
    comic_path: str = ""
    lightnovel_path: str = ""
    concurrent_downloads: int
    metadata_auto_lookup: bool
    default_schedule_interval: int
    sources: list[str]
    komga_url: str = ""
    komga_api_key_set: bool = False  # don't expose the key itself


class SettingsUpdate(BaseModel):
    concurrent_downloads: int | None = None
    metadata_auto_lookup: bool | None = None
    default_schedule_interval: int | None = None
    lightnovel_path: str | None = None
    komga_url: str | None = None
    komga_api_key: str | None = None
