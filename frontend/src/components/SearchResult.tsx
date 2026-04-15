import type { SearchResult as SearchResultType } from '../types';
import { proxyImage } from '../api';

interface Props {
  result: SearchResultType;
  onAdd: (result: SearchResultType) => void;
  /** Set of "source_name:source_id" strings already in the library */
  existingKeys?: Set<string>;
  /** Called when user clicks the "Open" button on an already-added result */
  onOpen?: (existingSeriesId: number) => void;
  /** Optional map from "source_name:source_id" to existing series id */
  existingIds?: Map<string, number>;
}

export default function SearchResult({ result, onAdd, existingKeys, onOpen, existingIds }: Props) {
  const key = `${result.source_name}:${result.source_id}`;
  const isAdded = existingKeys?.has(key) ?? false;
  const existingId = existingIds?.get(key);

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '12px 0',
      borderBottom: '1px solid #1e293b',
      opacity: isAdded ? 0.75 : 1,
    }}>
      <div style={{
        width: 40,
        height: 56,
        borderRadius: 4,
        overflow: 'hidden',
        flexShrink: 0,
        background: '#334155',
      }}>
        {result.cover_url && (
          <img
            src={proxyImage(result.cover_url) || ''}
            alt={result.title}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: '#e2e8f0', fontSize: 14, fontWeight: 500, marginBottom: 4,
          display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {result.title}
          </span>
          {isAdded && (
            <span style={{
              background: '#1e3a8a',
              color: '#93c5fd',
              fontSize: 9,
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: 3,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              flexShrink: 0,
            }}>
              In library
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {result.chapter_count != null && (
            <span style={{ color: '#64748b', fontSize: 12 }}>
              {result.chapter_count} chapters
            </span>
          )}
          {result.status && (() => {
            const s = result.status.toLowerCase();
            const styles: Record<string, { bg: string; fg: string; label: string }> = {
              ongoing:   { bg: '#14532d', fg: '#4ade80', label: 'Ongoing' },
              complete:  { bg: '#1e293b', fg: '#94a3b8', label: 'Completed' },
              completed: { bg: '#1e293b', fg: '#94a3b8', label: 'Completed' },
              hiatus:    { bg: '#78350f', fg: '#fbbf24', label: 'Hiatus' },
              dropped:   { bg: '#7f1d1d', fg: '#fca5a5', label: 'Dropped' },
            };
            const c = styles[s] || { bg: '#1e293b', fg: '#94a3b8', label: result.status };
            return (
              <span style={{
                background: c.bg, color: c.fg, fontSize: 10, fontWeight: 700,
                padding: '2px 7px', borderRadius: 12, textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}>
                {c.label}
              </span>
            );
          })()}
          <span style={{
            background: '#166534',
            color: '#4ade80',
            fontSize: 10,
            fontWeight: 600,
            padding: '2px 7px',
            borderRadius: 12,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}>
            {result.source_name}
          </span>
        </div>
      </div>

      {isAdded && existingId != null && onOpen ? (
        <button
          onClick={() => onOpen(existingId)}
          style={{
            background: 'transparent',
            color: '#93c5fd',
            border: '1px solid #1e3a8a',
            borderRadius: 6,
            padding: '7px 14px',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          Open
        </button>
      ) : (
        <button
          onClick={() => onAdd(result)}
          style={{
            background: isAdded ? '#475569' : '#a78bfa',
            color: isAdded ? '#cbd5e1' : '#0f172a',
            border: 'none',
            borderRadius: 6,
            padding: '7px 16px',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          {isAdded ? 'Re-add' : 'Add'}
        </button>
      )}
    </div>
  );
}
