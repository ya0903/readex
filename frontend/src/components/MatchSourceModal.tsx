import { useEffect, useState } from 'react';
import { api, proxyImage } from '../api';
import type { SearchResult, AppSettings } from '../types';

interface Props {
  open: boolean;
  initialQuery: string;
  onClose: () => void;
  onConfirm: (result: SearchResult) => void;
}

export default function MatchSourceModal({ open, initialQuery, onClose, onConfirm }: Props) {
  const [sources, setSources] = useState<string[]>([]);
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setQuery(initialQuery);
    setResults([]);
    setError(null);
    api.getSettings().then((s: AppSettings) => setSources(s.sources)).catch(() => setSources([]));
  }, [open, initialQuery]);

  if (!open) return null;

  const toggleSource = (name: string) => {
    setSelectedSources(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  async function doSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const sourceList = selectedSources.size > 0 ? Array.from(selectedSources) : undefined;
      const r = await api.search(query.trim(), sourceList);
      setResults(r);
      if (r.length === 0) setError('No matches found. Try a different query or sources.');
    } catch (e) {
      setError('Search failed: ' + String(e));
    } finally {
      setLoading(false);
    }
  }

  const overlayStyle: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  };
  const modalStyle: React.CSSProperties = {
    background: '#1e293b', borderRadius: 10, padding: 24,
    width: 600, maxWidth: '95vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column',
  };
  const inputStyle: React.CSSProperties = {
    width: '100%', background: '#0f172a', border: '1px solid #334155',
    borderRadius: 6, color: '#e2e8f0', fontSize: 13, padding: '8px 10px',
    outline: 'none', boxSizing: 'border-box',
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ color: '#e2e8f0', fontSize: 18, fontWeight: 700, marginTop: 0, marginBottom: 6 }}>
          Match to Source
        </h2>
        <p style={{ color: '#64748b', fontSize: 12, marginBottom: 14 }}>
          Pick a source result to bind this series to a scraper. Existing chapters
          stay on disk; new chapters from the source will be added as "available".
        </p>

        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <input
            style={inputStyle}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            placeholder="Search query..."
          />
          <button onClick={doSearch} disabled={loading}
            style={{ background: '#a78bfa', border: 'none', borderRadius: 6,
              color: '#0f172a', fontSize: 13, fontWeight: 700, padding: '8px 16px',
              cursor: loading ? 'wait' : 'pointer' }}>
            {loading ? '...' : 'Search'}
          </button>
        </div>

        {sources.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase',
              letterSpacing: 0.5, marginBottom: 4 }}>
              Sources {selectedSources.size === 0 ? '(all)' : `(${selectedSources.size})`}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {sources.map(s => {
                const active = selectedSources.has(s);
                return (
                  <button key={s} onClick={() => toggleSource(s)}
                    style={{
                      background: active ? '#a78bfa' : 'transparent',
                      border: active ? 'none' : '1px solid #334155',
                      borderRadius: 4, color: active ? '#0f172a' : '#94a3b8',
                      fontSize: 10, fontWeight: 600, padding: '3px 8px',
                      cursor: 'pointer',
                    }}>
                    {s}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {error && (
          <div style={{ color: '#f87171', fontSize: 12, marginBottom: 10 }}>{error}</div>
        )}

        <div style={{ overflowY: 'auto', flex: 1, marginBottom: 12, minHeight: 100 }}>
          {results.map((r, i) => (
            <div key={`${r.source_name}-${r.source_id}-${i}`}
              onClick={() => onConfirm(r)}
              style={{
                background: '#0f172a', borderRadius: 6, padding: '10px 12px',
                marginBottom: 6, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10,
                border: '1px solid transparent',
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = '#a78bfa')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'transparent')}>
              {r.cover_url && (
                <img src={proxyImage(r.cover_url) || ''} alt="" style={{ width: 32, height: 44, objectFit: 'cover',
                  borderRadius: 3, flexShrink: 0 }} />
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: '#e2e8f0', fontSize: 13, fontWeight: 500,
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {r.title}
                </div>
                <div style={{ color: '#64748b', fontSize: 11 }}>
                  {r.chapter_count != null && `${r.chapter_count} ch · `}
                  {r.status ?? 'unknown'}
                </div>
              </div>
              <span style={{ background: '#064e3b', color: '#6ee7b7', fontSize: 10,
                fontWeight: 600, padding: '3px 8px', borderRadius: 3,
                textTransform: 'uppercase', letterSpacing: 0.5 }}>
                {r.source_name}
              </span>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={onClose}
            style={{ background: 'transparent', border: '1px solid #334155',
              color: '#94a3b8', borderRadius: 6, fontSize: 13, padding: '8px 18px',
              cursor: 'pointer' }}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
