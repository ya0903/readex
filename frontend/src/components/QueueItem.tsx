import type { QueueItem as QueueItemType } from '../types';

interface Props {
  item: QueueItemType;
}

function statusColor(status: string): string {
  switch (status) {
    case 'active': return '#3b82f6';
    case 'pending': return '#f59e0b';
    case 'done': return '#22c55e';
    case 'failed': return '#ef4444';
    default: return '#64748b';
  }
}

export default function QueueItem({ item }: Props) {
  const color = statusColor(item.status);

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '10px 0',
      borderBottom: '1px solid #1e293b',
    }}>
      <div style={{ flex: 1, minWidth: 0, marginRight: 12 }}>
        <div style={{
          color: '#e2e8f0',
          fontSize: 13,
          fontWeight: 500,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {item.series_title} — Ch. {item.chapter_number}
        </div>
        {item.status === 'active' ? (
          <>
            <div style={{
              marginTop: 6,
              height: 3,
              borderRadius: 2,
              background: '#1e293b',
              overflow: 'hidden',
            }}>
              {item.progress_total > 0 ? (
                <div style={{
                  height: '100%',
                  width: `${Math.round((item.progress_current / item.progress_total) * 100)}%`,
                  background: '#3b82f6',
                  borderRadius: 2,
                  transition: 'width 0.3s ease',
                }} />
              ) : (
                <div style={{
                  height: '100%',
                  width: '40%',
                  background: '#3b82f6',
                  borderRadius: 2,
                  animation: 'indeterminate 1.4s ease-in-out infinite',
                }} />
              )}
            </div>
            {item.progress_total > 0 && (
              <div style={{ color: '#64748b', fontSize: 10, marginTop: 3 }}>
                page {item.progress_current} / {item.progress_total}
              </div>
            )}
          </>
        ) : (
          <div style={{ color: '#64748b', fontSize: 11, marginTop: 3 }}>
            {item.error_message ? item.error_message : item.status}
          </div>
        )}
      </div>
      <div style={{
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        color,
        flexShrink: 0,
      }}>
        {item.status}
      </div>

      <style>{`
        @keyframes indeterminate {
          0% { transform: translateX(-200%); width: 40%; }
          100% { transform: translateX(350%); width: 40%; }
        }
      `}</style>
    </div>
  );
}
