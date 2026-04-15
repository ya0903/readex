import type { Chapter } from '../types';

interface Props {
  chapter: Chapter;
  onDownload?: (id: number) => void;
  onToggleSelect?: (id: number) => void;
  selected?: boolean;
}

function statusInfo(status: string): { label: string; color: string } {
  switch (status) {
    case 'downloaded': return { label: 'Downloaded', color: '#22c55e' };
    case 'available': return { label: 'Available', color: '#f59e0b' };
    case 'queued': return { label: 'Queued', color: '#3b82f6' };
    case 'downloading': return { label: 'Downloading', color: '#3b82f6' };
    case 'failed': return { label: 'Failed', color: '#ef4444' };
    default: return { label: status, color: '#64748b' };
  }
}

export default function ChapterRow({ chapter, onDownload, onToggleSelect, selected }: Props) {
  const { label, color } = statusInfo(chapter.status);

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      padding: '9px 0',
      borderBottom: '1px solid #1e293b',
      gap: 10,
    }}>
      {onToggleSelect && (
        <input
          type="checkbox"
          checked={!!selected}
          onChange={() => onToggleSelect(chapter.id)}
          style={{ accentColor: '#a78bfa', flexShrink: 0 }}
        />
      )}

      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ color: '#e2e8f0', fontSize: 13 }}>
          Ch. {chapter.chapter_number}
          {chapter.title ? ` — ${chapter.title}` : ''}
        </span>
      </div>

      <div style={{
        fontSize: 11,
        fontWeight: 600,
        color,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        flexShrink: 0,
      }}>
        {label}
      </div>

      {chapter.status === 'available' && onDownload && (
        <button
          onClick={() => onDownload(chapter.id)}
          style={{
            background: '#a78bfa',
            color: '#0f172a',
            border: 'none',
            borderRadius: 4,
            padding: '4px 10px',
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          Download
        </button>
      )}
    </div>
  );
}
