import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { Series } from '../types';
import SeriesCard from '../components/SeriesCard';

type FilterType = 'all' | 'manga' | 'manhwa' | 'comic' | 'lightnovel' | 'ongoing' | 'complete';
type SortType = 'recent' | 'alpha' | 'chapters';

const FILTER_OPTIONS: { value: FilterType; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'manga', label: 'Manga' },
  { value: 'manhwa', label: 'Manhwa' },
  { value: 'comic', label: 'Comics' },
  { value: 'lightnovel', label: 'Light Novels' },
  { value: 'ongoing', label: 'Ongoing' },
  { value: 'complete', label: 'Complete' },
];

const SORT_OPTIONS: { value: SortType; label: string }[] = [
  { value: 'recent', label: 'Recent' },
  { value: 'alpha', label: 'Alphabetical' },
  { value: 'chapters', label: 'Chapter Count' },
];

function applyFilter(series: Series[], filter: FilterType): Series[] {
  switch (filter) {
    case 'manga': return series.filter((s) => s.content_type === 'manga');
    case 'manhwa': return series.filter((s) => s.content_type === 'manhwa');
    case 'comic': return series.filter((s) => s.content_type === 'comic');
    case 'lightnovel': return series.filter((s) => s.content_type === 'lightnovel');
    case 'ongoing': return series.filter((s) => s.status === 'ongoing');
    case 'complete': return series.filter((s) => s.status === 'complete');
    default: return series;
  }
}

function applySort(series: Series[], sort: SortType): Series[] {
  const copy = [...series];
  switch (sort) {
    case 'alpha':
      return copy.sort((a, b) => a.title.localeCompare(b.title));
    case 'chapters':
      return copy.sort((a, b) => b.chapter_count - a.chapter_count);
    case 'recent':
    default:
      return copy.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
  }
}

const selectStyle: React.CSSProperties = {
  background: '#1e293b',
  border: '1px solid #334155',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: 13,
  padding: '6px 10px',
  cursor: 'pointer',
  outline: 'none',
};

export default function Library() {
  const [series, setSeries] = useState<Series[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterType>('all');
  const [sort, setSort] = useState<SortType>('recent');
  const [query, setQuery] = useState('');
  const [selectionMode, setSelectionMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [syncStatus, setSyncStatus] = useState<{
    status: 'idle' | 'running' | 'done' | 'error';
    total: number;
    processed: number;
    updated: number;
    skipped: number;
    failed: number;
    failed_list: { id: number; title: string; reason: string }[];
    current: string | null;
  } | null>(null);
  const [resultDismissed, setResultDismissed] = useState(false);

  // Poll sync status — runs continuously when something's in progress so it
  // survives page navigation / reload. Shows the last completed run too.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const s = await api.getMetadataSyncStatus();
        if (!cancelled) setSyncStatus(s);
      } catch {}
    };
    tick();
    const interval = setInterval(() => {
      if (syncStatus?.status === 'running' || syncStatus === null) tick();
    }, 2500);
    return () => { cancelled = true; clearInterval(interval); };
  }, [syncStatus?.status]);

  // When sync just finished, reload the library to pick up new statuses/covers.
  useEffect(() => {
    if (syncStatus?.status === 'done' && syncStatus.processed === syncStatus.total) {
      reload();
    }
  }, [syncStatus?.status]);

  async function syncAllMetadata(event?: React.MouseEvent) {
    if (syncStatus?.status === 'running') return;
    // Shift-click = force re-sync everything (even already-synced ones).
    // Useful if Komga lost its metadata and needs a full rewrite.
    const force = !!event?.shiftKey;
    const prompt = force
      ? 'FORCE re-sync metadata + cover art for EVERY series (including ones already synced)?\n\nThis runs in the background.'
      : 'Sync metadata + cover art for series that haven\'t been synced yet (or whose metadata URL changed)?\n\nAlready-synced series will be skipped. Shift-click to force a full re-sync.\n\nThis runs in the background.';
    if (!window.confirm(prompt)) return;
    setResultDismissed(false);
    try {
      await api.startMetadataSync(force);
      const s = await api.getMetadataSyncStatus();
      setSyncStatus(s);
    } catch (e) {
      alert('Failed to start sync: ' + (e as Error).message);
    }
  }

  const reload = () => {
    api.listSeries().then(setSeries).catch(() => setError('Failed to load library'));
  };

  const toggleSelect = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  async function retryFailedForSelected() {
    if (busy || selected.size === 0) return;
    setBusy(true);
    try {
      const r = await api.retryFailedForSeries(Array.from(selected));
      alert(`Re-queued ${r.retried} failed download${r.retried === 1 ? '' : 's'}.`);
      setSelected(new Set());
      setSelectionMode(false);
      reload();
    } catch (e) {
      alert('Retry failed: ' + (e as Error).message);
    } finally { setBusy(false); }
  }

  async function deleteSelected(deleteFiles: boolean) {
    if (busy || selected.size === 0) return;
    const n = selected.size;
    const msg = deleteFiles
      ? `Permanently DELETE ${n} series AND their files on disk?\n\nThis cannot be undone.`
      : `Remove ${n} series from Readex's library? Files on disk will be kept.`;
    if (!window.confirm(msg)) return;
    setBusy(true);
    try {
      let removed = 0;
      for (const id of selected) {
        try {
          await api.deleteSeries(id, deleteFiles);
          removed++;
        } catch {}
      }
      alert(`Removed ${removed} of ${n} series.`);
      setSelected(new Set());
      setSelectionMode(false);
      reload();
    } finally { setBusy(false); }
  }

  useEffect(() => {
    api.listSeries()
      .then(setSeries)
      .catch(() => setError('Failed to load library'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: '#64748b', padding: 20 }}>Loading...</div>;
  if (error) return <div style={{ color: '#ef4444', padding: 20 }}>{error}</div>;

  const q = query.trim().toLowerCase();
  const filtered = q
    ? series.filter((s) =>
        s.title.toLowerCase().includes(q) ||
        s.folder_name.toLowerCase().includes(q)
      )
    : series;
  const displayed = applySort(applyFilter(filtered, filter), sort);

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      {/* Header row */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 20,
        marginTop: 4,
        flexWrap: 'wrap',
        gap: 12,
      }}>
        <h1 style={{ color: '#e2e8f0', fontSize: 22, fontWeight: 700, margin: 0 }}>
          Library
          <span style={{ color: '#475569', fontSize: 15, fontWeight: 400, marginLeft: 10 }}>
            {q ? `${displayed.length} of ${series.length}` : `${series.length}`} series
          </span>
        </h1>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative' }}>
            <input
              type="search"
              placeholder="Search library..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{
                background: '#1e293b',
                border: '1px solid #334155',
                borderRadius: 6,
                color: '#e2e8f0',
                fontSize: 13,
                padding: '6px 28px 6px 10px',
                outline: 'none',
                minWidth: 200,
              }}
              autoFocus
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                aria-label="Clear"
                style={{
                  position: 'absolute',
                  right: 4,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  fontSize: 16,
                  cursor: 'pointer',
                  padding: '0 6px',
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            )}
          </div>

          <select
            style={selectStyle}
            value={filter}
            onChange={(e) => setFilter(e.target.value as FilterType)}
          >
            {FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <select
            style={selectStyle}
            value={sort}
            onChange={(e) => setSort(e.target.value as SortType)}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <button
            onClick={syncAllMetadata}
            disabled={syncStatus?.status === 'running'}
            style={{
              ...selectStyle,
              background: '#1e293b',
              color: '#a78bfa',
              border: '1px solid #a78bfa',
              cursor: syncStatus?.status === 'running' ? 'wait' : 'pointer',
              opacity: syncStatus?.status === 'running' ? 0.6 : 1,
            }}
          >
            {syncStatus?.status === 'running'
              ? `Syncing… ${syncStatus.processed}/${syncStatus.total}`
              : 'Sync Metadata'}
          </button>

          <button
            onClick={() => {
              setSelectionMode(v => !v);
              setSelected(new Set());
            }}
            style={{
              ...selectStyle,
              background: selectionMode ? '#a78bfa' : selectStyle.background,
              color: selectionMode ? '#0f172a' : selectStyle.color,
              fontWeight: selectionMode ? 700 : 400,
              border: selectionMode ? 'none' : selectStyle.border,
            }}
          >
            {selectionMode ? 'Cancel' : 'Select'}
          </button>
        </div>
      </div>

      {/* Sync progress / results panel */}
      {syncStatus && syncStatus.status !== 'idle' && !resultDismissed && (
        <div style={{
          background: '#1e293b', borderRadius: 8, padding: 16, marginBottom: 14,
          border: syncStatus.status === 'running'
            ? '1px solid #1e3a8a'
            : (syncStatus.failed > 0 ? '1px solid #78350f' : '1px solid #14532d'),
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            marginBottom: syncStatus.failed_list.length ? 12 : 0 }}>
            <div style={{ flex: 1 }}>
              <div style={{ color: '#e2e8f0', fontSize: 14, fontWeight: 700, marginBottom: 2 }}>
                {syncStatus.status === 'running'
                  ? 'Metadata Sync Running…'
                  : syncStatus.status === 'error'
                    ? 'Metadata Sync Errored'
                    : 'Metadata Sync Complete'}
              </div>
              <div style={{ color: '#94a3b8', fontSize: 12 }}>
                {syncStatus.status === 'running'
                  ? `${syncStatus.processed} / ${syncStatus.total} processed${syncStatus.current ? ' · ' + syncStatus.current : ''}`
                  : (
                    <>
                      Updated {syncStatus.updated}
                      {(syncStatus.skipped ?? 0) > 0 && (
                        <span style={{ color: '#64748b' }}> · {syncStatus.skipped} already up to date</span>
                      )}
                      {' · '}
                      <span style={{ color: syncStatus.failed > 0 ? '#fbbf24' : '#22c55e', fontWeight: 600 }}>
                        {syncStatus.failed} need manual setup
                      </span>
                    </>
                  )}
              </div>
              {syncStatus.status === 'running' && syncStatus.total > 0 && (
                <div style={{ marginTop: 8, height: 4, background: '#0f172a',
                  borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{
                    width: `${Math.round((syncStatus.processed / syncStatus.total) * 100)}%`,
                    height: '100%', background: '#a78bfa',
                    transition: 'width 0.3s ease',
                  }} />
                </div>
              )}
            </div>
            {syncStatus.status !== 'running' && (
              <button onClick={() => setResultDismissed(true)}
                style={{ background: 'transparent', border: '1px solid #334155',
                  color: '#94a3b8', borderRadius: 5, fontSize: 11, padding: '4px 10px',
                  cursor: 'pointer', marginLeft: 12 }}>
                Dismiss
              </button>
            )}
          </div>

          {syncStatus.status !== 'running' && syncStatus.failed_list.length > 0 && (
            <>
              <div style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase',
                letterSpacing: 0.5, marginBottom: 6 }}>
                Couldn't auto-match — paste a metadata URL on each:
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4,
                maxHeight: 240, overflowY: 'auto', paddingRight: 4 }}>
                {syncStatus.failed_list.map(f => (
                  <Link key={f.id} to={`/series/${f.id}`}
                    style={{
                      background: '#0f172a', borderRadius: 5, padding: '8px 12px',
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      gap: 10, textDecoration: 'none',
                    }}>
                    <span style={{ color: '#e2e8f0', fontSize: 13, flex: 1, minWidth: 0,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {f.title}
                    </span>
                    <span style={{ color: '#fbbf24', fontSize: 11 }}>{f.reason}</span>
                    <span style={{ color: '#a78bfa', fontSize: 11, fontWeight: 600 }}>
                      Open →
                    </span>
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Sticky action bar — shown while in selection mode */}
      {selectionMode && (
        <div style={{
          position: 'sticky', top: 8, zIndex: 5,
          background: '#1e293b', borderRadius: 8, padding: '10px 14px',
          marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10,
          border: '1px solid #a78bfa', flexWrap: 'wrap',
        }}>
          <span style={{ color: '#e2e8f0', fontSize: 13, flex: 1 }}>
            {selected.size} selected
          </span>
          <button
            onClick={() => setSelected(new Set(displayed.map(s => s.id)))}
            style={{
              background: 'transparent', border: '1px solid #334155',
              color: '#94a3b8', borderRadius: 5, fontSize: 12,
              padding: '6px 12px', cursor: 'pointer',
            }}
          >
            Select all visible
          </button>
          <button
            onClick={retryFailedForSelected}
            disabled={busy || selected.size === 0}
            style={{
              background: '#3b82f6', border: 'none', borderRadius: 5,
              color: '#fff', fontSize: 12, fontWeight: 700,
              padding: '6px 14px',
              cursor: busy || selected.size === 0 ? 'not-allowed' : 'pointer',
              opacity: selected.size === 0 ? 0.5 : 1,
            }}
          >
            Retry Failed Downloads
          </button>
          <button
            onClick={() => deleteSelected(false)}
            disabled={busy || selected.size === 0}
            style={{
              background: 'transparent', border: '1px solid #334155',
              color: '#e2e8f0', borderRadius: 5, fontSize: 12,
              padding: '6px 14px',
              cursor: busy || selected.size === 0 ? 'not-allowed' : 'pointer',
              opacity: selected.size === 0 ? 0.5 : 1,
            }}
          >
            Remove from Readex
          </button>
          <button
            onClick={() => deleteSelected(true)}
            disabled={busy || selected.size === 0}
            style={{
              background: 'transparent', border: '1px solid #7f1d1d',
              color: '#fca5a5', borderRadius: 5, fontSize: 12,
              padding: '6px 14px',
              cursor: busy || selected.size === 0 ? 'not-allowed' : 'pointer',
              opacity: selected.size === 0 ? 0.5 : 1,
            }}
          >
            Delete (with files)
          </button>
        </div>
      )}

      {displayed.length === 0 ? (
        <div style={{ color: '#475569', textAlign: 'center', marginTop: 60, fontSize: 15 }}>
          {series.length === 0
            ? 'Your library is empty. Search for series to add them.'
            : q
              ? `No series match "${query}".`
              : 'No series match the current filter.'}
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: 14,
        }}>
          {displayed.map((s) => (
            <SeriesCard
              key={s.id}
              series={s}
              selectionMode={selectionMode}
              selected={selected.has(s.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
