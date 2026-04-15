import { useEffect, useState } from 'react';
import { api } from '../api';

interface ScanRow {
  folder: string;
  chapter_count: number;
  total_size: number;
  already_imported: boolean;
}

function fmtSize(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

export default function Import() {
  const [rows, setRows] = useState<ScanRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState('');
  const [contentType, setContentType] = useState<'manga' | 'manhwa' | 'comic'>('manga');
  const [importing, setImporting] = useState(false);
  const [resultMsg, setResultMsg] = useState<string | null>(null);

  async function scan() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.scanLibrary();
      setRows(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { scan(); }, []);

  const visibleRows = rows.filter(r =>
    !filter || r.folder.toLowerCase().includes(filter.toLowerCase())
  );
  const selectableRows = visibleRows.filter(r => !r.already_imported);

  const toggle = (folder: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(folder)) next.delete(folder); else next.add(folder);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(selectableRows.map(r => r.folder)));
  const clearAll = () => setSelected(new Set());

  const doImport = async () => {
    if (selected.size === 0) return;
    setImporting(true);
    setResultMsg(null);
    try {
      const result = await api.importFolders(Array.from(selected), contentType);
      const ok = result.filter(r => r.series_id != null && !r.error).length;
      const errors = result.filter(r => r.error).length;
      setResultMsg(`Imported ${ok} series — ${errors} errors.`);
      setSelected(new Set());
      await scan();
    } catch (e) {
      setResultMsg('Import failed: ' + String(e));
    } finally {
      setImporting(false);
    }
  };

  const cardStyle: React.CSSProperties = { background: '#1e293b', borderRadius: 8, padding: 16 };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: 22, fontWeight: 700, marginBottom: 6, marginTop: 4 }}>
        Import Library
      </h1>
      <p style={{ color: '#64748b', fontSize: 12, marginBottom: 18 }}>
        Scans your library folder for series Readex doesn't already track (e.g. existing
        Kaizoku downloads). Imported series can later be matched to a source for updates.
      </p>

      {error && (
        <div style={{ background: '#7f1d1d', color: '#fecaca', padding: '10px 14px',
          borderRadius: 6, fontSize: 13, marginBottom: 14 }}>{error}</div>
      )}
      {resultMsg && (
        <div style={{ background: '#14532d', color: '#bbf7d0', padding: '10px 14px',
          borderRadius: 6, fontSize: 13, marginBottom: 14 }}>{resultMsg}</div>
      )}

      <div style={{ ...cardStyle, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 12 }}>
        <input
          placeholder="Filter folders..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{ flex: 1, background: '#0f172a', border: '1px solid #334155', borderRadius: 6,
            color: '#e2e8f0', fontSize: 13, padding: '8px 10px', outline: 'none' }}
        />
        <select
          value={contentType}
          onChange={e => setContentType(e.target.value as 'manga' | 'manhwa' | 'comic')}
          style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 6,
            color: '#e2e8f0', fontSize: 13, padding: '8px 10px', cursor: 'pointer' }}
        >
          <option value="manga">Manga</option>
          <option value="manhwa">Manhwa</option>
          <option value="comic">Comic</option>
        </select>
        <button onClick={scan} disabled={loading}
          style={{ background: 'transparent', border: '1px solid #334155', color: '#94a3b8',
            borderRadius: 6, padding: '8px 14px', fontSize: 12, cursor: 'pointer' }}>
          {loading ? 'Scanning...' : 'Re-scan'}
        </button>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div style={{ fontSize: 12, color: '#64748b' }}>
          {visibleRows.length} folder{visibleRows.length === 1 ? '' : 's'}
          {selected.size > 0 && ` — ${selected.size} selected`}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={selectAll}
            style={{ background: 'transparent', border: '1px solid #334155', color: '#94a3b8',
              borderRadius: 4, padding: '4px 10px', fontSize: 11, cursor: 'pointer' }}>
            Select all importable
          </button>
          <button onClick={clearAll}
            style={{ background: 'transparent', border: '1px solid #334155', color: '#94a3b8',
              borderRadius: 4, padding: '4px 10px', fontSize: 11, cursor: 'pointer' }}>
            Clear
          </button>
          <button onClick={doImport} disabled={selected.size === 0 || importing}
            style={{ background: selected.size === 0 ? '#475569' : '#a78bfa',
              border: 'none', color: '#0f172a', borderRadius: 4, padding: '4px 14px',
              fontSize: 12, fontWeight: 700,
              cursor: selected.size === 0 ? 'not-allowed' : 'pointer' }}>
            {importing ? 'Importing...' : `Import ${selected.size}`}
          </button>
        </div>
      </div>

      <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
        {loading && rows.length === 0 && (
          <div style={{ padding: 24, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
            Scanning library…
          </div>
        )}
        {!loading && visibleRows.length === 0 && (
          <div style={{ padding: 24, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
            No matching folders.
          </div>
        )}
        {visibleRows.map(r => {
          const checked = selected.has(r.folder);
          return (
            <label key={r.folder}
              onClick={() => !r.already_imported && toggle(r.folder)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 16px', borderBottom: '1px solid #0f172a',
                cursor: r.already_imported ? 'not-allowed' : 'pointer',
                opacity: r.already_imported ? 0.5 : 1,
              }}>
              <input type="checkbox" checked={checked} disabled={r.already_imported}
                onChange={() => toggle(r.folder)}
                style={{ accentColor: '#a78bfa' }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: '#e2e8f0', fontSize: 13, fontWeight: 500,
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {r.folder}
                </div>
                <div style={{ color: '#64748b', fontSize: 11, marginTop: 2 }}>
                  {r.chapter_count} chapters · {fmtSize(r.total_size)}
                  {r.already_imported && (
                    <span style={{ color: '#22c55e', marginLeft: 8 }}>· already imported</span>
                  )}
                </div>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
