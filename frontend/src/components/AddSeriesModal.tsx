import { useState, useEffect } from 'react';
import type { SearchResult } from '../types';
import { api, type ChapterPreview } from '../api';

interface Props {
  result: SearchResult | null;
  onClose: () => void;
  onConfirm: (data: {
    title: string;
    folder_name: string;
    schedule_interval: number | null;
    metadata_url: string | null;
    selected_chapter_ids: string[]; // source_chapter_ids the user wants downloaded now
  }) => void;
}

const SCHEDULE_OPTIONS = [
  { label: 'Never', value: null },
  { label: 'Every 6 hours', value: 21600 },
  { label: 'Every 12 hours', value: 43200 },
  { label: 'Daily', value: 86400 },
  { label: 'Weekly', value: 604800 },
] as const;

function toFolderName(title: string): string {
  // Keep human-readable: only strip filesystem-illegal characters
  return title.replace(/[\\/:*?"<>|]/g, '').trim();
}

export default function AddSeriesModal({ result, onClose, onConfirm }: Props) {
  const [title, setTitle] = useState('');
  const [folderName, setFolderName] = useState('');
  const [scheduleInterval, setScheduleInterval] = useState<number | null>(null);
  const [metadataUrl, setMetadataUrl] = useState('');

  const [chapters, setChapters] = useState<ChapterPreview[] | null>(null);
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const [chaptersError, setChaptersError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [downloadMode, setDownloadMode] = useState<'all' | 'none' | 'select'>('all');

  useEffect(() => {
    if (!result) return;
    setTitle(result.title);
    setFolderName(toFolderName(result.title));
    setScheduleInterval(null);
    setMetadataUrl('');
    setChapters(null);
    setChaptersError(null);
    setSelectedIds(new Set());
    setDownloadMode('all');

    setChaptersLoading(true);
    api
      .previewChapters(result.source_name, result.source_id)
      .then((data) => {
        setChapters(data);
        setSelectedIds(new Set(data.map((c) => c.source_chapter_id)));
      })
      .catch((e) => setChaptersError(String(e)))
      .finally(() => setChaptersLoading(false));
  }, [result]);

  if (!result) return null;

  const toggleOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setDownloadMode('select');
  };

  const handleConfirm = () => {
    let ids: string[];
    if (downloadMode === 'all') ids = chapters?.map((c) => c.source_chapter_id) ?? [];
    else if (downloadMode === 'none') ids = [];
    else ids = Array.from(selectedIds);

    onConfirm({
      title: title.trim(),
      folder_name: folderName.trim(),
      schedule_interval: scheduleInterval,
      metadata_url: metadataUrl.trim() || null,
      selected_chapter_ids: ids,
    });
  };

  const overlayStyle: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  };
  const modalStyle: React.CSSProperties = {
    background: '#1e293b', borderRadius: 10, padding: 28,
    width: 560, maxWidth: '95vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block', color: '#64748b', fontSize: 11, fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6,
  };
  const inputStyle: React.CSSProperties = {
    width: '100%', background: '#0f172a', border: '1px solid #334155',
    borderRadius: 6, color: '#e2e8f0', fontSize: 13, padding: '8px 10px',
    outline: 'none', boxSizing: 'border-box',
  };
  const radioRow: React.CSSProperties = {
    display: 'flex', gap: 12, marginBottom: 8, fontSize: 12, color: '#e2e8f0',
  };

  const allSelected = chapters && selectedIds.size === chapters.length;

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
          <h2 style={{ color: '#e2e8f0', fontSize: 18, fontWeight: 700, margin: 0, flex: 1 }}>
            Add to Library
          </h2>
          <span style={{ background: '#334155', color: '#a78bfa', fontSize: 11, fontWeight: 600,
            padding: '3px 8px', borderRadius: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            {result.source_name}
          </span>
        </div>

        <div style={{ overflowY: 'auto', paddingRight: 6 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div>
              <label style={labelStyle}>Title</label>
              <input style={inputStyle} value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>Folder Name</label>
              <input style={inputStyle} value={folderName}
                onChange={(e) => setFolderName(e.target.value)} />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={labelStyle}>Schedule</label>
              <select style={{ ...inputStyle, cursor: 'pointer' }}
                value={scheduleInterval ?? 'null'}
                onChange={(e) => {
                  const v = e.target.value;
                  setScheduleInterval(v === 'null' ? null : Number(v));
                }}>
                {SCHEDULE_OPTIONS.map((opt) => (
                  <option key={String(opt.value)} value={String(opt.value)}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Metadata URL (optional)</label>
              <input style={inputStyle} placeholder="https://anilist.co/manga/..."
                value={metadataUrl} onChange={(e) => setMetadataUrl(e.target.value)} />
            </div>
          </div>

          <label style={labelStyle}>Chapters</label>
          {chaptersLoading && (
            <div style={{ fontSize: 12, color: '#64748b', padding: '12px 0' }}>Loading chapter list…</div>
          )}
          {chaptersError && (
            <div style={{ fontSize: 12, color: '#f87171', padding: '12px 0' }}>
              Could not fetch chapters: {chaptersError}
            </div>
          )}
          {chapters && chapters.length === 0 && (
            <div style={{ fontSize: 12, color: '#f59e0b', padding: '12px 0' }}>
              No chapters found from this source.
            </div>
          )}
          {chapters && chapters.length > 0 && (
            <>
              <div style={radioRow}>
                <label style={{ cursor: 'pointer' }}>
                  <input type="radio" checked={downloadMode === 'all'}
                    onChange={() => setDownloadMode('all')} /> All ({chapters.length})
                </label>
                <label style={{ cursor: 'pointer' }}>
                  <input type="radio" checked={downloadMode === 'none'}
                    onChange={() => setDownloadMode('none')} /> Track only (download none)
                </label>
                <label style={{ cursor: 'pointer' }}>
                  <input type="radio" checked={downloadMode === 'select'}
                    onChange={() => setDownloadMode('select')} /> Pick chapters
                </label>
              </div>
              {downloadMode === 'select' && (
                <>
                  <div style={{ display: 'flex', gap: 10, marginBottom: 6 }}>
                    <button onClick={() => setSelectedIds(new Set(chapters.map((c) => c.source_chapter_id)))}
                      style={{ background: 'transparent', border: '1px solid #334155',
                        color: '#94a3b8', borderRadius: 4, padding: '3px 10px', fontSize: 11, cursor: 'pointer' }}>
                      Select all
                    </button>
                    <button onClick={() => setSelectedIds(new Set())}
                      style={{ background: 'transparent', border: '1px solid #334155',
                        color: '#94a3b8', borderRadius: 4, padding: '3px 10px', fontSize: 11, cursor: 'pointer' }}>
                      Clear
                    </button>
                  </div>
                  <div style={{ maxHeight: 220, overflowY: 'auto', background: '#0f172a',
                    border: '1px solid #334155', borderRadius: 6, padding: 4 }}>
                    {chapters.map((ch) => {
                      const checked = selectedIds.has(ch.source_chapter_id);
                      return (
                        <label key={ch.source_chapter_id}
                          style={{ display: 'flex', alignItems: 'center', gap: 8,
                            padding: '4px 6px', cursor: 'pointer', fontSize: 12, color: '#e2e8f0' }}>
                          <input type="checkbox" checked={checked}
                            onChange={() => toggleOne(ch.source_chapter_id)} />
                          <span>Chapter {ch.chapter_number}</span>
                          {ch.title && <span style={{ color: '#64748b' }}>— {ch.title}</span>}
                        </label>
                      );
                    })}
                  </div>
                </>
              )}
              {downloadMode === 'all' && (
                <div style={{ fontSize: 11, color: '#64748b' }}>
                  All {chapters.length} chapters will be queued.
                </div>
              )}
              {downloadMode === 'none' && (
                <div style={{ fontSize: 11, color: '#64748b' }}>
                  Series tracked only — schedule will pick up new chapters going forward.
                </div>
              )}
              {allSelected && downloadMode === 'select' && (
                <div style={{ fontSize: 11, color: '#22c55e', marginTop: 4 }}>
                  All chapters selected.
                </div>
              )}
            </>
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
          <button onClick={onClose}
            style={{ background: 'transparent', border: '1px solid #334155',
              borderRadius: 6, color: '#94a3b8', fontSize: 13, padding: '8px 18px', cursor: 'pointer' }}>
            Cancel
          </button>
          <button onClick={handleConfirm} disabled={chaptersLoading}
            style={{ background: '#a78bfa', border: 'none', borderRadius: 6,
              color: '#0f172a', fontSize: 13, fontWeight: 700, padding: '8px 18px',
              cursor: chaptersLoading ? 'not-allowed' : 'pointer',
              opacity: chaptersLoading ? 0.6 : 1 }}>
            Add to Library
          </button>
        </div>
      </div>
    </div>
  );
}
