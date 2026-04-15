interface Props {
  label: string;
  value: number;
  color?: string;
}

export default function StatCard({ label, value, color = '#a78bfa' }: Props) {
  return (
    <div style={{
      background: '#1e293b',
      borderRadius: 8,
      padding: '20px 24px',
      flex: 1,
    }}>
      <div style={{
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: '#64748b',
        marginBottom: 8,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 28,
        fontWeight: 700,
        color,
        lineHeight: 1,
      }}>
        {value}
      </div>
    </div>
  );
}
