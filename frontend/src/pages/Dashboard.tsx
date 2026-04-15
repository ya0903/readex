import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { Series, QueueItem as QueueItemType, RecentDownload, Schedule } from '../types';
import StatCard from '../components/StatCard';
import QueueItem from '../components/QueueItem';

function formatInterval(seconds: number): string {
  if (seconds >= 604800) return 'Weekly';
  if (seconds >= 86400) return 'Daily';
  if (seconds >= 43200) return 'Every 12h';
  if (seconds >= 21600) return 'Every 6h';
  return `${Math.round(seconds / 3600)}h`;
}

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 0) return 'Overdue';
  if (diffMin < 60) return `in ${diffMin}m`;
  if (diffMin < 1440) return `in ${Math.round(diffMin / 60)}h`;
  return `in ${Math.round(diffMin / 1440)}d`;
}

export default function Dashboard() {
  const [series, setSeries] = useState<Series[]>([]);
  const [queue, setQueue] = useState<QueueItemType[]>([]);
  const [recent, setRecent] = useState<RecentDownload[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadStatic() {
    try {
      const [s, sc] = await Promise.all([api.listSeries(), api.listSchedules()]);
      setSeries(s);
      setSchedules(sc);
    } catch {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }

  async function loadLive() {
    try {
      const [q, r] = await Promise.all([api.getQueue(), api.getRecent(10)]);
      setQueue(q);
      setRecent(r);
    } catch {
      // silent on refresh errors
    }
  }

  useEffect(() => {
    loadStatic();
    loadLive();
    const interval = setInterval(loadLive, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div style={{ color: '#64748b', padding: 20 }}>Loading...</div>;
  if (error) return <div style={{ color: '#ef4444', padding: 20 }}>{error}</div>;

  const totalChapters = series.reduce((sum, s) => sum + s.chapter_count, 0);
  const enabledSchedules = schedules.filter((s) => s.enabled).length;
  const queueActive = queue.filter((q) => q.status === 'pending' || q.status === 'active').length;

  const sectionTitle: React.CSSProperties = {
    color: '#94a3b8',
    fontSize: 12,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: 12,
  };

  const card: React.CSSProperties = {
    background: '#1e293b',
    borderRadius: 8,
    padding: 16,
  };

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: 22, fontWeight: 700, marginBottom: 24, marginTop: 4 }}>
        Dashboard
      </h1>

      {/* Stat row */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 28, flexWrap: 'wrap' }}>
        <StatCard label="Total Series" value={series.length} color="#a78bfa" />
        <StatCard label="Chapters" value={totalChapters} color="#e2e8f0" />
        <StatCard label="Scheduled" value={enabledSchedules} color="#22c55e" />
        <StatCard label="Queue" value={queueActive} color="#f59e0b" />
      </div>

      {/* Two column section */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        {/* Download Queue */}
        <div style={card}>
          <div style={{ ...sectionTitle, display: 'flex', justifyContent: 'space-between',
            alignItems: 'center' }}>
            <span>Download Queue</span>
            <Link to="/queue" style={{ color: '#a78bfa', fontSize: 11, fontWeight: 600,
              textTransform: 'none', letterSpacing: 0 }}>
              View all →
            </Link>
          </div>
          {queue.length === 0 ? (
            <div style={{ color: '#475569', fontSize: 13 }}>Queue is empty</div>
          ) : (
            queue.slice(0, 8).map((item) => <QueueItem key={item.id} item={item} />)
          )}
          {queue.length > 8 && (
            <Link to="/queue" style={{ color: '#64748b', fontSize: 12, marginTop: 8,
              display: 'block', textAlign: 'center' }}>
              + {queue.length - 8} more in queue
            </Link>
          )}
        </div>

        {/* Recent Downloads */}
        <div style={card}>
          <div style={sectionTitle}>Recent Downloads</div>
          {recent.length === 0 ? (
            <div style={{ color: '#475569', fontSize: 13 }}>No recent downloads</div>
          ) : (
            recent.slice(0, 8).map((r) => (
              <div
                key={r.chapter_id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 0',
                  borderBottom: '1px solid #0f172a',
                }}
              >
                <div>
                  <div style={{ color: '#e2e8f0', fontSize: 13 }}>
                    {r.series_title}
                  </div>
                  <div style={{ color: '#64748b', fontSize: 11, marginTop: 2 }}>
                    Ch. {r.chapter_number} · {r.source_name}
                  </div>
                </div>
                <div style={{ color: '#475569', fontSize: 11 }}>
                  {r.downloaded_at ? new Date(r.downloaded_at).toLocaleDateString() : ''}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Upcoming schedules */}
      <div style={card}>
        <div style={sectionTitle}>Upcoming Scheduled Checks</div>
        {schedules.filter((s) => s.enabled).length === 0 ? (
          <div style={{ color: '#475569', fontSize: 13 }}>No active schedules</div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {schedules
              .filter((s) => s.enabled)
              .sort((a, b) => {
                if (!a.next_check_at) return 1;
                if (!b.next_check_at) return -1;
                return new Date(a.next_check_at).getTime() - new Date(b.next_check_at).getTime();
              })
              .map((s) => {
                const matched = series.find((sr) => sr.id === s.series_id);
                return (
                  <div
                    key={s.id}
                    style={{
                      background: '#0f172a',
                      borderRadius: 20,
                      padding: '5px 12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <span style={{ color: '#e2e8f0', fontSize: 12 }}>
                      {matched?.title ?? `Series #${s.series_id}`}
                    </span>
                    <span style={{ color: '#64748b', fontSize: 11 }}>
                      {formatInterval(s.interval_seconds)}
                    </span>
                    <span style={{
                      color: '#a78bfa',
                      fontSize: 11,
                      background: '#1e1040',
                      borderRadius: 10,
                      padding: '1px 7px',
                    }}>
                      {formatRelative(s.next_check_at)}
                    </span>
                  </div>
                );
              })}
          </div>
        )}
      </div>
    </div>
  );
}
