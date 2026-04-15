import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { SearchResult as SearchResultType } from '../types';
import SearchResultComponent from '../components/SearchResult';
import AddSeriesModal from '../components/AddSeriesModal';
import ConfirmReplaceModal from '../components/ConfirmReplaceModal';

type Tab = 'search' | 'url';

const inputStyle: React.CSSProperties = {
  background: '#1e293b',
  border: '1px solid #334155',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: 14,
  padding: '9px 12px',
  outline: 'none',
  flex: 1,
};

const btnStyle: React.CSSProperties = {
  background: '#a78bfa',
  border: 'none',
  borderRadius: 6,
  color: '#0f172a',
  fontSize: 13,
  fontWeight: 700,
  padding: '9px 20px',
  cursor: 'pointer',
  flexShrink: 0,
};

export default function Search() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('search');
  const [availableSources, setAvailableSources] = useState<string[]>([]);
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [existingKeys, setExistingKeys] = useState<Set<string>>(new Set());
  const [existingIds, setExistingIds] = useState<Map<string, number>>(new Map());

  const refreshLibrary = () => {
    api.listSeries().then(list => {
      const keys = new Set(list.map(s => `${s.source_name}:${s.source_id}`));
      const ids = new Map(list.map(s => [`${s.source_name}:${s.source_id}`, s.id]));
      setExistingKeys(keys);
      setExistingIds(ids);
    }).catch(() => {});
  };

  // Search tab
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultType[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // URL tab
  const [url, setUrl] = useState('');
  const [urlResult, setUrlResult] = useState<SearchResultType | null>(null);
  const [parsing, setParsing] = useState(false);
  const [urlError, setUrlError] = useState<string | null>(null);

  // Modal
  const [modalResult, setModalResult] = useState<SearchResultType | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Conflict resolution modal state — shown when create_series returns 409
  const [conflict, setConflict] = useState<null | {
    existingTitle: string;
    existingFolder: string;
    payload: Record<string, unknown>;
    formData: {
      schedule_interval: number | null;
      selected_chapter_ids: string[];
      title: string;
    };
  }>(null);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => setAvailableSources(s.sources))
      .catch(() => setAvailableSources([]));
    refreshLibrary();
  }, []);

  const toggleSource = (name: string) => {
    setSelectedSources((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  async function doSearch() {
    if (!query.trim()) return;
    setSearching(true);
    setSearchError(null);
    setResults([]);
    try {
      const sources = selectedSources.size > 0 ? Array.from(selectedSources) : undefined;
      const r = await api.search(query.trim(), sources);
      setResults(r);
    } catch {
      setSearchError('Search failed. Check your connection or source configuration.');
    } finally {
      setSearching(false);
    }
  }

  async function doParseUrl() {
    if (!url.trim()) return;
    setParsing(true);
    setUrlError(null);
    setUrlResult(null);
    try {
      const r = await api.parseUrl(url.trim());
      setUrlResult(r);
    } catch {
      setUrlError('Failed to parse URL. Check the URL and try again.');
    } finally {
      setParsing(false);
    }
  }

  async function finishSeriesSetup(
    created: { id: number },
    schedule_interval: number | null,
    selected_chapter_ids: string[],
    title: string,
  ) {
    try {
      if (schedule_interval != null) {
        await api.createSchedule({
          series_id: created.id,
          interval_seconds: schedule_interval,
          enabled: true,
        });
      }
      if (selected_chapter_ids.length > 0) {
        const detail = await api.getSeries(created.id);
        const availableIds = detail.chapters
          .filter((ch) => ch.status === 'available' || ch.status === 'queued')
          .map((ch) => ch.id);
        if (availableIds.length > 0) {
          if (selected_chapter_ids.length === detail.chapters.length) {
            await api.queueDownload(created.id);
          } else {
            const ids = availableIds.slice(0, selected_chapter_ids.length);
            if (ids.length > 0) await api.queueDownload(created.id, ids);
          }
        }
      }
      setModalResult(null);
      setSuccessMsg(`"${title}" added — ${selected_chapter_ids.length} chapters queued.`);
      setTimeout(() => setSuccessMsg(null), 4000);
      refreshLibrary();
    } catch (e) {
      alert('Series created but post-setup failed: ' + String(e));
    }
  }

  async function handleConflictResolve(deleteFiles: boolean) {
    if (!conflict) return;
    const { payload, formData } = conflict;
    setConflict(null);
    try {
      const created = await api.createSeries(payload, { replace: true, deleteFiles });
      await finishSeriesSetup(
        created,
        formData.schedule_interval,
        formData.selected_chapter_ids,
        formData.title,
      );
    } catch (e) {
      alert('Replace failed: ' + (e as Error).message);
    }
  }

  async function handleConfirm(data: {
    title: string;
    folder_name: string;
    schedule_interval: number | null;
    metadata_url: string | null;
    selected_chapter_ids: string[];
  }) {
    if (!modalResult) return;
    const payload = {
      title: data.title,
      folder_name: data.folder_name,
      source_name: modalResult.source_name,
      source_id: modalResult.source_id,
      content_type: modalResult.content_type,
      status: modalResult.status ?? 'ongoing',
      metadata_url: data.metadata_url,
      cover_url: modalResult.cover_url,
    };

    let created;
    try {
      created = await api.createSeries(payload);
    } catch (e) {
      const err = e as Error & { status?: number; detail?: { existing_title?: string; existing_folder?: string } };
      if (err.status === 409 && err.detail?.existing_title) {
        // Open the conflict modal; keep the original modal closed in the background
        setModalResult(null);
        setConflict({
          existingTitle: err.detail.existing_title,
          existingFolder: err.detail.existing_folder ?? data.folder_name,
          payload,
          formData: {
            schedule_interval: data.schedule_interval,
            selected_chapter_ids: data.selected_chapter_ids,
            title: data.title,
          },
        });
        return;
      }
      alert('Failed to add series: ' + (err.message || String(err)));
      return;
    }
    await finishSeriesSetup(
      created, data.schedule_interval, data.selected_chapter_ids, data.title,
    );
  }

  const tabBtn = (t: Tab, label: string) => (
    <button
      onClick={() => setTab(t)}
      style={{
        background: tab === t ? '#a78bfa' : 'transparent',
        border: tab === t ? 'none' : '1px solid #334155',
        borderRadius: 6,
        color: tab === t ? '#0f172a' : '#94a3b8',
        fontSize: 13,
        fontWeight: 600,
        padding: '7px 18px',
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: 22, fontWeight: 700, marginBottom: 20, marginTop: 4 }}>
        Search
      </h1>

      {successMsg && (
        <div style={{
          background: '#14532d',
          color: '#4ade80',
          borderRadius: 6,
          padding: '10px 16px',
          marginBottom: 16,
          fontSize: 13,
        }}>
          {successMsg}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {tabBtn('search', 'Search')}
        {tabBtn('url', 'Paste URL')}
      </div>

      {tab === 'search' && (
        <div>
          {availableSources.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase',
                letterSpacing: 0.5, marginBottom: 6 }}>
                Sources {selectedSources.size === 0 ? '(all)' : `(${selectedSources.size} selected)`}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {availableSources.map((s) => {
                  const active = selectedSources.has(s);
                  return (
                    <button key={s} onClick={() => toggleSource(s)}
                      style={{
                        background: active ? '#a78bfa' : 'transparent',
                        border: active ? 'none' : '1px solid #334155',
                        borderRadius: 4,
                        color: active ? '#0f172a' : '#94a3b8',
                        fontSize: 11,
                        fontWeight: 600,
                        padding: '4px 10px',
                        cursor: 'pointer',
                      }}>
                      {s}
                    </button>
                  );
                })}
                {selectedSources.size > 0 && (
                  <button onClick={() => setSelectedSources(new Set())}
                    style={{
                      background: 'transparent',
                      border: '1px solid #334155',
                      borderRadius: 4,
                      color: '#64748b',
                      fontSize: 11,
                      padding: '4px 10px',
                      cursor: 'pointer',
                    }}>clear</button>
                )}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            <input
              style={inputStyle}
              placeholder="Search for manga, manhwa, comics..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doSearch()}
            />
            <button style={btnStyle} onClick={doSearch} disabled={searching}>
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>

          {searchError && (
            <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>{searchError}</div>
          )}

          {!searching && results.length === 0 && query && !searchError && (
            <div style={{ color: '#475569', fontSize: 13 }}>No results found.</div>
          )}

          {results.map((r, i) => (
            <SearchResultComponent
              key={`${r.source_name}-${r.source_id}-${i}`}
              result={r}
              onAdd={setModalResult}
              existingKeys={existingKeys}
              existingIds={existingIds}
              onOpen={(id) => navigate(`/series/${id}`)}
            />
          ))}
        </div>
      )}

      {tab === 'url' && (
        <div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            <input
              style={inputStyle}
              placeholder="Paste series URL here..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doParseUrl()}
            />
            <button style={btnStyle} onClick={doParseUrl} disabled={parsing}>
              {parsing ? 'Parsing...' : 'Parse'}
            </button>
          </div>

          {urlError && (
            <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>{urlError}</div>
          )}

          {urlResult && (
            <SearchResultComponent
              result={urlResult}
              onAdd={setModalResult}
              existingKeys={existingKeys}
              existingIds={existingIds}
              onOpen={(id) => navigate(`/series/${id}`)}
            />
          )}
        </div>
      )}

      <AddSeriesModal
        result={modalResult}
        onClose={() => setModalResult(null)}
        onConfirm={handleConfirm}
      />

      <ConfirmReplaceModal
        open={conflict !== null}
        existingTitle={conflict?.existingTitle ?? ''}
        existingFolder={conflict?.existingFolder ?? ''}
        onCancel={() => setConflict(null)}
        onKeepFiles={() => handleConflictResolve(false)}
        onWipeFiles={() => handleConflictResolve(true)}
      />
    </div>
  );
}
