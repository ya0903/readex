import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { SeriesDetail as SeriesDetailType } from '../types';
import ChapterRow from '../components/ChapterRow';
import MatchSourceModal from '../components/MatchSourceModal';
import type { SearchResult } from '../types';

const COLORS = ['#7c3aed', '#dc2626', '#f59e0b', '#2563eb', '#059669', '#64748b'];
function hashColor(title: string): string {
  let hash = 0;
  for (const ch of title) hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
  return COLORS[Math.abs(hash) % COLORS.length];
}

function intervalLabel(seconds: number, checkTime: string | null): string {
  const timeSuffix = checkTime ? ` at ${checkTime}` : '';
  if (seconds >= 604800) return `Weekly${timeSuffix}`;
  if (seconds >= 86400) return `Daily${timeSuffix}`;
  if (seconds >= 43200) return 'Every 12 hours';
  if (seconds >= 21600) return 'Every 6 hours';
  return `Every ${Math.round(seconds / 3600)} hours`;
}

const SCHEDULE_OPTIONS = [
  { label: 'Never', value: 'null' },
  { label: 'Every 6 hours', value: '21600' },
  { label: 'Every 12 hours', value: '43200' },
  { label: 'Daily', value: '86400' },
  { label: 'Weekly', value: '604800' },
];

export default function SeriesDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const seriesId = Number(id);

  const [detail, setDetail] = useState<SeriesDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [matchOpen, setMatchOpen] = useState(false);

  // Edit schedule state
  const [editingSchedule, setEditingSchedule] = useState(false);
  const [scheduleVal, setScheduleVal] = useState('null');
  const [checkTime, setCheckTime] = useState<string>('');

  // Edit metadata state
  const [editingMeta, setEditingMeta] = useState(false);
  const [metaUrl, setMetaUrl] = useState('');

  // Rename state
  const [editingName, setEditingName] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newFolder, setNewFolder] = useState('');

  async function load() {
    try {
      const d = await api.getSeries(seriesId);
      setDetail(d);
      setMetaUrl(d.metadata_url ?? '');
      setNewTitle(d.title);
      setNewFolder(d.folder_name);
      setScheduleVal(d.schedule ? String(d.schedule.interval_seconds) : 'null');
      setCheckTime(d.schedule?.check_time ?? '');
    } catch {
      setError('Failed to load series');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [seriesId]);

  function flash(msg: string) {
    setActionMsg(msg);
    setTimeout(() => setActionMsg(null), 3000);
  }

  async function handleDownloadAll() {
    try {
      const result = await api.queueDownload(seriesId);
      flash(`Queued ${result.queued} chapters for download.`);
    } catch {
      flash('Failed to queue downloads.');
    }
  }

  async function handleDownloadChapter(chapterId: number) {
    try {
      await api.queueDownload(seriesId, [chapterId]);
      flash('Chapter queued for download.');
      load();
    } catch {
      flash('Failed to queue chapter.');
    }
  }

  async function handleDownloadSelected() {
    if (selectedIds.size === 0) return;
    try {
      const result = await api.queueDownload(seriesId, Array.from(selectedIds));
      flash(`Queued ${result.queued} chapters.`);
      setSelectedIds(new Set());
      load();
    } catch {
      flash('Failed to queue selected chapters.');
    }
  }

  async function handleSaveSchedule() {
    if (!detail) return;
    try {
      if (scheduleVal === 'null') {
        if (detail.schedule) {
          await api.deleteSchedule(detail.schedule.id);
        }
      } else {
        const secs = Number(scheduleVal);
        // Only send check_time for Daily/Weekly intervals
        const time = secs >= 86400 && checkTime ? checkTime : null;
        if (detail.schedule) {
          await api.updateSchedule(detail.schedule.id, { interval_seconds: secs, check_time: time, enabled: true });
        } else {
          await api.createSchedule({ series_id: seriesId, interval_seconds: secs, check_time: time, enabled: true });
        }
      }
      flash('Schedule saved.');
      setEditingSchedule(false);
      load();
    } catch {
      flash('Failed to save schedule.');
    }
  }

  async function handleSaveMeta() {
    if (!detail) return;
    try {
      await api.updateSeries(seriesId, { metadata_url: metaUrl.trim() || null });
      flash('Metadata link saved.');
      setEditingMeta(false);
      load();
    } catch {
      flash('Failed to save metadata link.');
    }
  }

  async function handleRemove(deleteFiles: boolean) {
    if (!detail) return;
    const msg = deleteFiles
      ? `Permanently delete "${detail.title}" AND all its CBZ files from disk?\n\nThis cannot be undone.`
      : `Remove "${detail.title}" from Readex's library? Files on disk will be kept.`;
    if (!window.confirm(msg)) return;
    try {
      await api.deleteSeries(seriesId, deleteFiles);
      navigate('/library');
    } catch {
      flash('Failed to remove series.');
    }
  }

  async function handleMatchSource(result: SearchResult) {
    try {
      const r = await api.matchSource(seriesId, result.source_name, result.source_id);
      setMatchOpen(false);
      await load();
      flash(`Matched to ${result.source_name} — linked ${r.linked} existing, added ${r.added} new chapters.`);
    } catch (e) {
      flash('Match failed: ' + String(e));
    }
  }

  async function handleSaveRename() {
    if (!detail) return;
    const t = newTitle.trim();
    const f = newFolder.trim();
    if (!t || !f) {
      flash('Title and folder name cannot be empty.');
      return;
    }
    if (t === detail.title && f === detail.folder_name) {
      setEditingName(false);
      return;
    }
    try {
      await api.updateSeries(seriesId, { title: t, folder_name: f });
      await load();
      setEditingName(false);
      flash(`Renamed${f !== detail.folder_name ? ' (folder moved on disk)' : ''}.`);
    } catch (e) {
      flash('Rename failed: ' + (e as Error).message);
    }
  }

  async function handleSyncMetadata() {
    try {
      const r = await api.syncMetadata(seriesId);
      const parts: string[] = [];
      if (r.wrote_series_json) parts.push('series.json');
      if (r.cover_file) parts.push(r.cover_file);
      let msg = parts.length
        ? `Wrote ${parts.join(' + ')}`
        : 'Metadata refreshed';
      if (r.komga_rescan_triggered) {
        msg += ' · Komga rescan triggered (summary should appear in ~10s)';
      } else if (r.komga_enabled) {
        msg += ' · Komga rescan skipped (debounced or no matching library)';
      } else {
        msg += ' · Komga rescan not configured (set API key in Settings)';
      }
      flash(msg);
      await load();  // refresh page so cover/title update right away
    } catch (e) {
      flash('Sync failed: ' + (e as Error).message);
    }
  }

  function toggleSelect(chapterId: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(chapterId)) next.delete(chapterId);
      else next.add(chapterId);
      return next;
    });
  }

  if (loading) return <div style={{ color: '#64748b', padding: 20 }}>Loading...</div>;
  if (error || !detail) return <div style={{ color: '#ef4444', padding: 20 }}>{error ?? 'Not found'}</div>;

  const fallbackColor = hashColor(detail.title);
  const downloaded = detail.chapters.filter((c) => c.status === 'downloaded').length;
  const available = detail.chapters.filter((c) => c.status === 'available').length;

  const sidebarBtnStyle: React.CSSProperties = {
    display: 'block',
    width: '100%',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 13,
    padding: '8px 12px',
    cursor: 'pointer',
    textAlign: 'left',
    marginBottom: 8,
  };

  const dangerBtnStyle: React.CSSProperties = {
    ...sidebarBtnStyle,
    color: '#f87171',
    borderColor: '#7f1d1d',
  };

  const inputStyle: React.CSSProperties = {
    background: '#0f172a',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 13,
    padding: '7px 10px',
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box',
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', gap: 24, alignItems: 'flex-start' }}>
      {/* Left sidebar */}
      <div style={{ width: 200, flexShrink: 0 }}>
        {/* Cover */}
        <div style={{
          width: '100%',
          paddingTop: '140%',
          position: 'relative',
          borderRadius: 8,
          overflow: 'hidden',
          background: fallbackColor,
          marginBottom: 16,
        }}>
          <div style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            background: `linear-gradient(135deg, ${fallbackColor}cc, ${fallbackColor}55)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 8,
          }}>
            <span style={{ color: '#fff', fontSize: 13, fontWeight: 600, textAlign: 'center' }}>
              {detail.title}
            </span>
          </div>
          <img
            src={`/api/series/${seriesId}/cover`}
            alt=""
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover' }}
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        </div>

        {/* Meta info */}
        <div style={{ marginBottom: 16 }}>
          <InfoLine label="Status" value={detail.status} />
          <InfoLine label="Type" value={detail.content_type} />
          <InfoLine label="Source" value={detail.source_name} />
          <InfoLine
            label="Schedule"
            value={detail.schedule ? intervalLabel(detail.schedule.interval_seconds, detail.schedule.check_time) : 'None'}
          />
          {detail.metadata_url && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ color: '#475569', fontSize: 11, marginBottom: 2 }}>Metadata</div>
              <a
                href={detail.metadata_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#a78bfa', fontSize: 12, wordBreak: 'break-all' }}
              >
                Link
              </a>
            </div>
          )}
        </div>

        {/* Actions */}
        <button style={sidebarBtnStyle} onClick={async () => {
          try {
            const r = await api.refreshSeries(seriesId);
            await load();
            flash(`Refreshed — ${r.added} new chapter${r.added === 1 ? '' : 's'} found.`);
          } catch (e) {
            flash('Refresh failed: ' + String(e));
          }
        }}>
          Refresh Chapters
        </button>

        <button style={sidebarBtnStyle} onClick={handleDownloadAll}>
          Download All Missing
        </button>

        {/* Edit Schedule */}
        <button style={sidebarBtnStyle} onClick={() => setEditingSchedule((v) => !v)}>
          Edit Schedule
        </button>
        {editingSchedule && (
          <div style={{ marginBottom: 10 }}>
            <select
              style={{ ...inputStyle, marginBottom: 6, cursor: 'pointer' }}
              value={scheduleVal}
              onChange={(e) => setScheduleVal(e.target.value)}
            >
              {SCHEDULE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            {/* Time picker — visible when Daily or Weekly is selected */}
            {Number(scheduleVal) >= 86400 && scheduleVal !== 'null' && (
              <div style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                <label style={{ color: '#94a3b8', fontSize: 11 }}>at</label>
                <input
                  type="time"
                  value={checkTime}
                  onChange={(e) => setCheckTime(e.target.value)}
                  style={{
                    ...inputStyle,
                    width: 'auto',
                    margin: 0,
                    padding: '3px 8px',
                    colorScheme: 'dark',
                  }}
                />
                {checkTime && (
                  <button
                    onClick={() => setCheckTime('')}
                    style={{
                      background: 'none', border: 'none', color: '#64748b',
                      fontSize: 11, cursor: 'pointer', padding: 0,
                    }}
                  >
                    clear
                  </button>
                )}
              </div>
            )}
            <button
              onClick={handleSaveSchedule}
              style={{
                background: '#a78bfa', border: 'none', borderRadius: 5,
                color: '#0f172a', fontSize: 12, fontWeight: 700,
                padding: '5px 12px', cursor: 'pointer',
              }}
            >
              Save
            </button>
          </div>
        )}

        {/* Edit Metadata */}
        <button style={sidebarBtnStyle} onClick={() => setEditingMeta((v) => !v)}>
          Edit Metadata Link
        </button>
        {editingMeta && (
          <div style={{ marginBottom: 10 }}>
            <input
              style={{ ...inputStyle, marginBottom: 6 }}
              placeholder="https://..."
              value={metaUrl}
              onChange={(e) => setMetaUrl(e.target.value)}
            />
            <button
              onClick={handleSaveMeta}
              style={{
                background: '#a78bfa', border: 'none', borderRadius: 5,
                color: '#0f172a', fontSize: 12, fontWeight: 700,
                padding: '5px 12px', cursor: 'pointer',
              }}
            >
              Save
            </button>
          </div>
        )}

        <button style={sidebarBtnStyle} onClick={() => setEditingName(v => !v)}>
          Rename
        </button>
        {editingName && (
          <div style={{ marginBottom: 10 }}>
            <input
              style={{ ...inputStyle, marginBottom: 6 }}
              placeholder="Title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
            <input
              style={{ ...inputStyle, marginBottom: 6 }}
              placeholder="Folder name"
              value={newFolder}
              onChange={(e) => setNewFolder(e.target.value)}
            />
            <div style={{ fontSize: 10, color: '#64748b', marginBottom: 6 }}>
              Changing folder name moves files on disk.
            </div>
            <button onClick={handleSaveRename}
              style={{ background: '#a78bfa', border: 'none', borderRadius: 5,
                color: '#0f172a', fontSize: 12, fontWeight: 700,
                padding: '5px 12px', cursor: 'pointer', width: '100%' }}>
              Save
            </button>
          </div>
        )}

        <button style={sidebarBtnStyle} onClick={() => setMatchOpen(true)}>
          {detail.source_name === 'imported' ? 'Match to Source' : 'Change Source'}
        </button>

        <button style={sidebarBtnStyle} onClick={handleSyncMetadata}>
          Sync Komga Metadata
        </button>

        <button style={sidebarBtnStyle} onClick={() => handleRemove(false)}>
          Remove from Readex
        </button>

        <button style={dangerBtnStyle} onClick={() => handleRemove(true)}>
          Delete (with files)
        </button>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Title & stats */}
        <h1 style={{ color: '#e2e8f0', fontSize: 24, fontWeight: 700, marginTop: 0, marginBottom: 6 }}>
          {detail.title}
        </h1>
        <div style={{ color: '#64748b', fontSize: 13, marginBottom: 16 }}>
          {detail.chapter_count} chapters · {downloaded} downloaded · {available} available
        </div>

        {actionMsg && (
          <div style={{
            background: '#172554',
            color: '#93c5fd',
            borderRadius: 6,
            padding: '8px 14px',
            fontSize: 13,
            marginBottom: 14,
          }}>
            {actionMsg}
          </div>
        )}

        {/* Bulk selection bar */}
        {selectedIds.size > 0 && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            background: '#1e293b',
            borderRadius: 6,
            padding: '10px 14px',
            marginBottom: 12,
          }}>
            <span style={{ color: '#e2e8f0', fontSize: 13 }}>{selectedIds.size} selected</span>
            <button
              onClick={handleDownloadSelected}
              style={{
                background: '#a78bfa', border: 'none', borderRadius: 5,
                color: '#0f172a', fontSize: 12, fontWeight: 700,
                padding: '5px 14px', cursor: 'pointer',
              }}
            >
              Download Selected
            </button>
            <button
              onClick={async () => {
                if (!detail) return;
                const n = selectedIds.size;
                const ok = window.confirm(
                  `Remove ${n} chapter${n === 1 ? '' : 's'} from Readex?\n\n` +
                  `Files on disk will be kept. You can also delete the CBZ files —\n` +
                  `click OK to remove DB rows only, or Cancel to skip.`
                );
                if (!ok) return;
                try {
                  const r = await api.deleteChapters(seriesId, Array.from(selectedIds), false);
                  setSelectedIds(new Set());
                  await load();
                  flash(`Removed ${r.removed} chapter${r.removed === 1 ? '' : 's'} from library.`);
                } catch (e) {
                  flash('Delete failed: ' + (e as Error).message);
                }
              }}
              style={{
                background: 'transparent', border: '1px solid #334155', borderRadius: 5,
                color: '#e2e8f0', fontSize: 12, padding: '5px 12px', cursor: 'pointer',
              }}
            >
              Remove from Library
            </button>
            <button
              onClick={async () => {
                if (!detail) return;
                const n = selectedIds.size;
                const ok = window.confirm(
                  `Permanently DELETE ${n} chapter${n === 1 ? '' : 's'} and their CBZ files on disk?\n\nThis cannot be undone.`
                );
                if (!ok) return;
                try {
                  const r = await api.deleteChapters(seriesId, Array.from(selectedIds), true);
                  setSelectedIds(new Set());
                  await load();
                  flash(`Deleted ${r.removed} chapters + ${r.files_removed} files.`);
                } catch (e) {
                  flash('Delete failed: ' + (e as Error).message);
                }
              }}
              style={{
                background: 'transparent', border: '1px solid #7f1d1d', borderRadius: 5,
                color: '#fca5a5', fontSize: 12, padding: '5px 12px', cursor: 'pointer',
              }}
            >
              Delete (with files)
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              style={{
                background: 'transparent', border: '1px solid #334155', borderRadius: 5,
                color: '#94a3b8', fontSize: 12, padding: '5px 12px', cursor: 'pointer',
              }}
            >
              Clear
            </button>
          </div>
        )}

        {/* Chapter list */}
        <div style={{ background: '#1e293b', borderRadius: 8, padding: '4px 16px' }}>
          {detail.chapters.length === 0 ? (
            <div style={{ color: '#475569', padding: '16px 0', fontSize: 13 }}>
              No chapters found. Try refreshing.
            </div>
          ) : (
            detail.chapters.map((ch) => (
              <ChapterRow
                key={ch.id}
                chapter={ch}
                onDownload={handleDownloadChapter}
                onToggleSelect={toggleSelect}
                selected={selectedIds.has(ch.id)}
              />
            ))
          )}
        </div>
      </div>

      <MatchSourceModal
        open={matchOpen}
        initialQuery={detail.title}
        onClose={() => setMatchOpen(false)}
        onConfirm={handleMatchSource}
      />
    </div>
  );
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ color: '#475569', fontSize: 11, marginBottom: 1 }}>{label}</div>
      <div style={{ color: '#e2e8f0', fontSize: 12, textTransform: 'capitalize' }}>{value}</div>
    </div>
  );
}
