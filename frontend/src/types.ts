export interface Series {
  id: number;
  title: string;
  folder_name: string;
  source_name: string;
  source_id: string;
  content_type: string;
  status: string;
  metadata_url: string | null;
  metadata_synced_at: string | null;
  cover_url: string | null;
  created_at: string;
  updated_at: string;
  chapter_count: number;
  downloaded_count: number;
}

export interface Chapter {
  id: number;
  series_id: number;
  chapter_number: number;
  title: string | null;
  status: string;
  file_path: string | null;
  downloaded_at: string | null;
}

export interface SeriesDetail extends Series {
  chapters: Chapter[];
  schedule: Schedule | null;
}

export interface SearchResult {
  source_name: string;
  source_id: string;
  title: string;
  cover_url: string | null;
  content_type: string;
  chapter_count: number | null;
  status: string | null;
  url: string;
}

export interface QueueItem {
  id: number;
  chapter_id: number;
  series_title: string;
  chapter_number: number;
  priority: number;
  status: string;
  error_message: string | null;
  retries: number;
  progress_current: number;
  progress_total: number;
  created_at: string;
}

export interface Schedule {
  id: number;
  series_id: number;
  interval_seconds: number;
  check_time: string | null;
  check_day_of_week: number | null;
  last_checked_at: string | null;
  next_check_at: string | null;
  enabled: boolean;
}

export interface RecentDownload {
  chapter_id: number;
  series_title: string;
  series_id: number;
  chapter_number: number;
  source_name: string;
  downloaded_at: string | null;
}

export interface AppSettings {
  library_path: string;
  manga_path: string;
  manhwa_path: string;
  comic_path: string;
  lightnovel_path: string;
  komga_url: string;
  komga_api_key_set: boolean;
  concurrent_downloads: number;
  metadata_auto_lookup: boolean;
  default_schedule_interval: number;
  sources: string[];
}
