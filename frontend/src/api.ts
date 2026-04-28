import type {
  Series, SeriesDetail, SearchResult, QueueItem,
  Schedule, RecentDownload, AppSettings,
} from './types';

const BASE = '/api';

/**
 * Wrap an external image URL so it goes through our backend proxy.
 * Many manga site CDNs require a Referer that browsers can't set on `<img>` tags;
 * the proxy fetches with the right Referer and returns the bytes.
 * Returns null if the input is null/undefined so consumers can fall back.
 */
export function proxyImage(url: string | null | undefined): string | null {
  if (!url) return null;
  // Already a relative path (our own static) — leave alone
  if (!/^https?:\/\//i.test(url)) return url;
  return `/api/proxy/image?url=${encodeURIComponent(url)}`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    let detail: unknown = '';
    let message = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      detail = body?.detail ?? body;
      if (typeof detail === 'string') {
        message = detail;
      } else if (detail && typeof detail === 'object' && 'message' in (detail as object)) {
        message = String((detail as { message: unknown }).message);
      } else {
        message = JSON.stringify(detail);
      }
    } catch {
      try { message = (await resp.text()) || message; } catch { /* ignore */ }
    }
    const err = new Error(message) as Error & { status?: number; detail?: unknown };
    err.status = resp.status;
    err.detail = detail;
    throw err;
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export interface ChapterPreview {
  source_chapter_id: string;
  chapter_number: number;
  title: string | null;
  url: string;
}

export const api = {
  listSeries: () => request<Series[]>('/series'),
  getSeries: (id: number) => request<SeriesDetail>(`/series/${id}`),
  createSeries: (data: Partial<Series>, opts?: { replace?: boolean; deleteFiles?: boolean }) => {
    const params = new URLSearchParams();
    if (opts?.replace) params.set('replace', 'true');
    if (opts?.deleteFiles) params.set('delete_files', 'true');
    const qs = params.toString();
    return request<Series>(`/series${qs ? '?' + qs : ''}`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  updateSeries: (id: number, data: Partial<Series>) =>
    request<Series>(`/series/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteSeries: (id: number, deleteFiles: boolean = false) =>
    request<void>(`/series/${id}?delete_files=${deleteFiles}`, { method: 'DELETE' }),
  refreshSeries: (id: number) =>
    request<{ added: number; total: number }>(`/series/${id}/refresh`, { method: 'POST' }),
  scanSeriesFiles: (id: number) =>
    request<{ scanned: number; updated: number; missing: number }>(
      `/series/${id}/scan-files`, { method: 'POST' }
    ),
  deleteChapters: (seriesId: number, chapterIds: number[], deleteFiles: boolean = false) =>
    request<{ removed: number; files_removed: number }>(
      `/series/${seriesId}/chapters/delete`,
      {
        method: 'POST',
        body: JSON.stringify({ chapter_ids: chapterIds, delete_files: deleteFiles }),
      }
    ),
  syncMetadata: (id: number) =>
    request<{
      written: string;
      wrote_series_json: boolean;
      cover_file: string | null;
      komga_enabled: boolean;
      komga_rescan_triggered: boolean;
    }>(`/series/${id}/metadata/sync`, { method: 'POST' }),
  startMetadataSync: (force: boolean = false) =>
    request<{ status: string; force?: boolean; message?: string }>(
      `/series/metadata/sync-all${force ? '?force=true' : ''}`,
      { method: 'POST' }
    ),
  getMetadataSyncStatus: () =>
    request<{
      status: 'idle' | 'running' | 'done' | 'error';
      started_at: string | null;
      finished_at: string | null;
      total: number;
      processed: number;
      updated: number;
      skipped: number;
      failed: number;
      failed_list: { id: number; title: string; reason: string }[];
      current: string | null;
    }>('/series/metadata/sync-all/status'),
  matchSource: (id: number, source_name: string, source_id: string) =>
    request<{ linked: number; added: number }>(`/series/${id}/match-source`, {
      method: 'POST',
      body: JSON.stringify({ source_name, source_id }),
    }),
  scanLibrary: () =>
    request<{ folder: string; chapter_count: number; total_size: number; already_imported: boolean }[]>(
      '/import/scan'
    ),
  importFolders: (folders: string[], content_type: string = 'manga') =>
    request<{ folder: string; series_id: number | null; chapters: number; error: string | null }[]>(
      '/import/import',
      { method: 'POST', body: JSON.stringify({ folders, content_type }) }
    ),

  search: (query: string, sources?: string[]) =>
    request<SearchResult[]>('/search', {
      method: 'POST',
      body: JSON.stringify({ query, sources }),
    }),
  parseUrl: (url: string) =>
    request<SearchResult>('/search/url', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  previewChapters: (source_name: string, source_id: string) =>
    request<ChapterPreview[]>(
      `/search/preview?source_name=${encodeURIComponent(source_name)}&source_id=${encodeURIComponent(source_id)}`
    ),

  queueDownload: (seriesId: number, chapterIds?: number[]) =>
    request<{ queued: number }>('/downloads', {
      method: 'POST',
      body: JSON.stringify({ series_id: seriesId, chapter_ids: chapterIds }),
    }),
  getQueue: () => request<QueueItem[]>('/downloads/queue'),
  retryFailedForSeries: (seriesIds: number[]) =>
    request<{ retried: number }>('/downloads/series-retry-failed', {
      method: 'POST',
      body: JSON.stringify({ series_ids: seriesIds }),
    }),
  retryQueueItems: (queueIds: number[], allFailed: boolean = false) =>
    request<{ retried: number }>('/downloads/queue/retry', {
      method: 'POST',
      body: JSON.stringify({ queue_ids: queueIds, all_failed: allFailed }),
    }),
  deleteQueueItems: (queueIds: number[], status?: string) =>
    request<{ removed: number }>('/downloads/queue/delete', {
      method: 'POST',
      body: JSON.stringify(status ? { status } : { queue_ids: queueIds }),
    }),
  getRecent: (limit = 20) => request<RecentDownload[]>(`/downloads/recent?limit=${limit}`),

  listSchedules: () => request<Schedule[]>('/schedules'),
  createSchedule: (data: { series_id: number; interval_seconds: number; check_time?: string | null; check_day_of_week?: number | null; enabled?: boolean }) =>
    request<Schedule>('/schedules', { method: 'POST', body: JSON.stringify(data) }),
  updateSchedule: (id: number, data: Partial<Schedule>) =>
    request<Schedule>(`/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteSchedule: (id: number) =>
    request<void>(`/schedules/${id}`, { method: 'DELETE' }),

  getSettings: () => request<AppSettings>('/settings'),
  updateSettings: (data: Partial<AppSettings>) =>
    request<AppSettings>('/settings', { method: 'PATCH', body: JSON.stringify(data) }),
};
