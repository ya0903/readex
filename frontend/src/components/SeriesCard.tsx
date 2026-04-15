import { useNavigate } from 'react-router-dom';
import type { Series } from '../types';

const COLORS = ['#7c3aed', '#dc2626', '#f59e0b', '#2563eb', '#059669', '#64748b'];
function hashColor(title: string): string {
  let hash = 0;
  for (const ch of title) hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
  return COLORS[Math.abs(hash) % COLORS.length];
}

function statusBadge(series: Series): { label: string; color: string } {
  if (series.content_type === 'comic') return { label: 'Comic', color: '#f59e0b' };
  if (series.status === 'ongoing') return { label: 'Ongoing', color: '#22c55e' };
  if (series.status === 'complete') return { label: 'Complete', color: '#64748b' };
  return { label: series.status, color: '#64748b' };
}

interface Props {
  series: Series;
  selectionMode?: boolean;
  selected?: boolean;
  onToggleSelect?: (id: number) => void;
}

export default function SeriesCard({ series, selectionMode, selected, onToggleSelect }: Props) {
  const navigate = useNavigate();
  const badge = statusBadge(series);
  const fallbackColor = hashColor(series.title);

  const handleClick = () => {
    if (selectionMode && onToggleSelect) {
      onToggleSelect(series.id);
    } else {
      navigate(`/series/${series.id}`);
    }
  };

  return (
    <div
      onClick={handleClick}
      style={{
        cursor: 'pointer',
        width: '100%',
        position: 'relative',
        outline: selected ? '3px solid #a78bfa' : 'none',
        outlineOffset: 2,
        borderRadius: 6,
      }}
    >
      {/* Cover area — 2:3 aspect ratio */}
      <div style={{
        position: 'relative',
        paddingTop: '150%',
        borderRadius: 6,
        overflow: 'hidden',
        background: fallbackColor,
      }}>
        {/* Title-gradient placeholder always rendered behind the img.
            If the cover loads, it covers this. If the request 404s, it stays visible. */}
        <div style={{
          position: 'absolute',
          top: 0, left: 0,
          width: '100%', height: '100%',
          background: `linear-gradient(135deg, ${fallbackColor}cc, ${fallbackColor}55)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 8,
        }}>
          <span style={{
            color: '#fff',
            fontSize: 12,
            fontWeight: 600,
            textAlign: 'center',
            lineHeight: 1.3,
            wordBreak: 'break-word',
          }}>
            {series.title}
          </span>
        </div>
        {/* Always try /api/series/{id}/cover — backend serves cover.{jpg|png|webp}
            from disk if present, else proxies series.cover_url. */}
        <img
          src={`/api/series/${series.id}/cover`}
          alt=""
          style={{
            position: 'absolute',
            top: 0, left: 0,
            width: '100%', height: '100%',
            objectFit: 'cover',
          }}
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
        {/* Selection checkbox overlay (only visible in selection mode) */}
        {selectionMode && (
          <div style={{
            position: 'absolute', top: 6, left: 6, zIndex: 5,
            width: 22, height: 22, borderRadius: '50%',
            background: selected ? '#a78bfa' : 'rgba(15,23,42,0.7)',
            border: selected ? 'none' : '2px solid rgba(255,255,255,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 14, fontWeight: 700,
          }}>
            {selected ? '✓' : ''}
          </div>
        )}
        {/* Status badge top-right */}
        <div style={{
          position: 'absolute',
          top: 6,
          right: 6,
          background: badge.color,
          color: '#fff',
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          padding: '2px 6px',
          borderRadius: 4,
        }}>
          {badge.label}
        </div>
        {/* Source badge bottom-left over a subtle gradient */}
        <div style={{
          position: 'absolute',
          left: 0, right: 0, bottom: 0,
          padding: '14px 6px 6px',
          background: 'linear-gradient(to top, rgba(15,23,42,0.92), rgba(15,23,42,0))',
          display: 'flex',
          justifyContent: 'flex-start',
        }}>
          <span style={{
            background: 'rgba(167,139,250,0.85)',
            color: '#0f172a',
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            padding: '2px 6px',
            borderRadius: 3,
          }}>
            {series.source_name}
          </span>
        </div>
      </div>
      {/* Info below card */}
      <div style={{ marginTop: 6 }}>
        <div style={{
          color: '#e2e8f0',
          fontSize: 12,
          fontWeight: 600,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {series.title}
        </div>
        <div style={{
          color: '#64748b', fontSize: 11, marginTop: 2,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>{series.chapter_count} ch</span>
          {series.downloaded_count > 0 && (
            <span style={{ color: '#22c55e' }}>{series.downloaded_count} ↓</span>
          )}
        </div>
      </div>
    </div>
  );
}
