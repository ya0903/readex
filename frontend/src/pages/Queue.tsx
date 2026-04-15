import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { QueueItem } from '../types';

const STATUS_COLORS: Record<string, { bg: string; fg: string }> = {
  active: { bg: '#1e3a8a', fg: '#93c5fd' },
  pending: { bg: '#334155', fg: '#cbd5e1' },
  failed: { bg: '#7f1d1d', fg: '#fecaca' },
  complete: { bg: '#14532d', fg: '#bbf7d0' },
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function Queue() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await api.getQueue();
      setItems(r);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  const grouped = {
    active: items.filter(i => i.status === 'active'),
    pending: items.filter(i => i.status === 'pending'),
    failed: items.filter(i => i.status === 'failed'),
  };

  const toggle = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllInGroup = (group: QueueItem[]) => {
    setSelected(prev => {
      const next = new Set(prev);
      group.forEach(i => next.add(i.id));
      return next;
    });
  };

  async function retry(ids: number[]) {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.retryQueueItems(ids);
      setSelected(new Set());
      await load();
      alert(`Retrying ${r.retried} download${r.retried === 1 ? '' : 's'}.`);
    } catch (e) {
      alert('Retry failed: ' + (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function retryAllFailed() {
    if (busy || grouped.failed.length === 0) return;
    if (!window.confirm(`Retry all ${grouped.failed.length} failed downloads?`)) return;
    setBusy(true);
    try {
      const r = await api.retryQueueItems([], true);
      setSelected(new Set());
      await load();
      alert(`Retrying ${r.retried} download${r.retried === 1 ? '' : 's'}.`);
    } catch (e) {
      alert('Retry failed: ' + (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(ids: number[]) {
    if (busy || ids.length === 0) return;
    if (!window.confirm(`Remove ${ids.length} item${ids.length === 1 ? '' : 's'} from the queue?\n\nFiles already downloaded are kept; chapters reset to "available".`)) return;
    setBusy(true);
    try {
      const r = await api.deleteQueueItems(ids);
      setSelected(new Set());
      await load();
      alert(`Removed ${r.removed} from queue.`);
    } catch (e) {
      alert('Delete failed: ' + (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function clearAllFailed() {
    if (busy || grouped.failed.length === 0) return;
    if (!window.confirm(`Remove all ${grouped.failed.length} failed items from the queue?`)) return;
    setBusy(true);
    try {
      const r = await api.deleteQueueItems([], 'failed');
      setSelected(new Set());
      await load();
      alert(`Removed ${r.removed} failed items.`);
    } catch (e) {
      alert('Delete failed: ' + (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const card: React.CSSProperties = { background: '#1e293b', borderRadius: 8, padding: 16, marginBottom: 14 };
  const tinyBtn: React.CSSProperties = {
    background: 'transparent', border: '1px solid #334155',
    color: '#94a3b8', borderRadius: 4, padding: '3px 10px',
    fontSize: 11, fontWeight: 600, cursor: 'pointer',
  };

  const renderItem = (item: QueueItem) => {
    const c = STATUS_COLORS[item.status] || STATUS_COLORS.pending;
    const pct = item.progress_total > 0
      ? Math.round((item.progress_current / item.progress_total) * 100)
      : 0;
    const isSelected = selected.has(item.id);
    return (
      <div key={item.id} style={{
        background: isSelected ? '#1e293b' : '#0f172a',
        borderLeft: isSelected ? '3px solid #a78bfa' : '3px solid transparent',
        borderRadius: 6, padding: '10px 12px',
        marginBottom: 6,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => toggle(item.id)}
            style={{ accentColor: '#a78bfa', cursor: 'pointer' }}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: '#e2e8f0', fontSize: 13, fontWeight: 500,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {item.series_title} <span style={{ color: '#94a3b8', fontWeight: 400 }}>
                — Ch. {item.chapter_number}
              </span>
            </div>
            <div style={{ color: '#64748b', fontSize: 11, marginTop: 2,
              display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>queued {timeAgo(item.created_at)}</span>
              {item.retries > 0 && (
                <span style={{ color: '#f59e0b' }}>· {item.retries} retr{item.retries === 1 ? 'y' : 'ies'}</span>
              )}
              {item.status === 'active' && item.progress_total > 0 && (
                <span style={{ color: '#93c5fd' }}>
                  · page {item.progress_current} / {item.progress_total}
                </span>
              )}
            </div>
            {item.error_message && (
              <div style={{ color: '#f87171', fontSize: 11, marginTop: 4,
                fontFamily: 'monospace', wordBreak: 'break-word' }}>
                {item.error_message}
              </div>
            )}
          </div>
          <span style={{
            background: c.bg, color: c.fg, fontSize: 10, fontWeight: 700,
            padding: '3px 8px', borderRadius: 4, textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}>
            {item.status}
          </span>
        </div>
        {item.status === 'active' && (
          <div style={{ marginTop: 8, height: 4, background: '#1e293b',
            borderRadius: 2, overflow: 'hidden' }}>
            {item.progress_total > 0 ? (
              <div style={{
                width: `${pct}%`, height: '100%', background: '#a78bfa',
                transition: 'width 0.3s ease',
              }} />
            ) : (
              <div style={{
                width: '40%', height: '100%', background: '#a78bfa',
                animation: 'readex-loading 1.4s ease-in-out infinite',
              }} />
            )}
          </div>
        )}
      </div>
    );
  };

  const sectionHeader = (label: string, color: string, group: QueueItem[]) => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      marginBottom: 10 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color, textTransform: 'uppercase',
        letterSpacing: '0.05em' }}>
        {label} ({group.length})
      </div>
      <button onClick={() => selectAllInGroup(group)} style={tinyBtn}>
        Select all
      </button>
    </div>
  );

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <h1 style={{ color: '#e2e8f0', fontSize: 22, fontWeight: 700, margin: 0 }}>
          Download Queue
        </h1>
        <Link to="/" style={{ color: '#64748b', fontSize: 12 }}>← Dashboard</Link>
      </div>

      {error && (
        <div style={{ background: '#7f1d1d', color: '#fecaca', padding: '10px 14px',
          borderRadius: 6, fontSize: 13, marginBottom: 14 }}>
          {error}
        </div>
      )}

      {/* Selection action bar */}
      {selected.size > 0 && (
        <div style={{
          position: 'sticky', top: 8, zIndex: 5,
          background: '#1e293b', borderRadius: 8, padding: '10px 14px',
          marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10,
          border: '1px solid #a78bfa',
        }}>
          <span style={{ color: '#e2e8f0', fontSize: 13, flex: 1 }}>
            {selected.size} selected
          </span>
          <button onClick={() => retry(Array.from(selected))} disabled={busy}
            style={{ background: '#3b82f6', border: 'none', borderRadius: 5,
              color: '#fff', fontSize: 12, fontWeight: 700,
              padding: '6px 14px', cursor: busy ? 'wait' : 'pointer' }}>
            Retry
          </button>
          <button onClick={() => remove(Array.from(selected))} disabled={busy}
            style={{ background: 'transparent', border: '1px solid #7f1d1d',
              color: '#fca5a5', borderRadius: 5, fontSize: 12,
              padding: '6px 14px', cursor: busy ? 'wait' : 'pointer' }}>
            Remove
          </button>
          <button onClick={() => setSelected(new Set())} disabled={busy}
            style={{ background: 'transparent', border: '1px solid #334155',
              color: '#94a3b8', borderRadius: 5, fontSize: 12,
              padding: '6px 12px', cursor: 'pointer' }}>
            Clear
          </button>
        </div>
      )}

      {/* Quick action bar — visible when there are failed items */}
      {grouped.failed.length > 0 && selected.size === 0 && (
        <div style={{ background: '#1e293b', borderRadius: 8, padding: '10px 14px',
          marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ color: '#fecaca', fontSize: 13, flex: 1 }}>
            {grouped.failed.length} failed download{grouped.failed.length === 1 ? '' : 's'}
          </span>
          <button onClick={retryAllFailed} disabled={busy}
            style={{ background: '#3b82f6', border: 'none', borderRadius: 5,
              color: '#fff', fontSize: 12, fontWeight: 700,
              padding: '6px 14px', cursor: busy ? 'wait' : 'pointer' }}>
            Retry all failed
          </button>
          <button onClick={clearAllFailed} disabled={busy}
            style={{ background: 'transparent', border: '1px solid #7f1d1d',
              color: '#fca5a5', borderRadius: 5, fontSize: 12,
              padding: '6px 14px', cursor: busy ? 'wait' : 'pointer' }}>
            Clear all failed
          </button>
        </div>
      )}

      {loading && items.length === 0 && (
        <div style={{ color: '#64748b', padding: 24, textAlign: 'center' }}>Loading…</div>
      )}

      {!loading && items.length === 0 && !error && (
        <div style={{ background: '#1e293b', borderRadius: 8, padding: 32, textAlign: 'center',
          color: '#64748b', fontSize: 14 }}>
          The queue is empty. Add a series and queue some chapters.
        </div>
      )}

      {grouped.failed.length > 0 && (
        <div style={card}>
          {sectionHeader('Failed', '#fecaca', grouped.failed)}
          {grouped.failed.map(renderItem)}
        </div>
      )}

      {grouped.active.length > 0 && (
        <div style={card}>
          {sectionHeader('Active', '#93c5fd', grouped.active)}
          {grouped.active.map(renderItem)}
        </div>
      )}

      {grouped.pending.length > 0 && (
        <div style={card}>
          {sectionHeader('Pending', '#cbd5e1', grouped.pending)}
          {grouped.pending.slice(0, 100).map(renderItem)}
          {grouped.pending.length > 100 && (
            <div style={{ color: '#64748b', fontSize: 12, marginTop: 8, textAlign: 'center' }}>
              + {grouped.pending.length - 100} more…
            </div>
          )}
        </div>
      )}
    </div>
  );
}
