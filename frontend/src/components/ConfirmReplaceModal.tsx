interface Props {
  open: boolean;
  existingTitle: string;
  existingFolder: string;
  onCancel: () => void;
  onKeepFiles: () => void;
  onWipeFiles: () => void;
}

export default function ConfirmReplaceModal({
  open, existingTitle, existingFolder, onCancel, onKeepFiles, onWipeFiles,
}: Props) {
  if (!open) return null;

  const overlay: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100,
  };
  const modal: React.CSSProperties = {
    background: '#1e293b', borderRadius: 10, padding: 28,
    width: 480, maxWidth: '92vw',
  };
  const optionRow: React.CSSProperties = {
    background: '#0f172a', borderRadius: 6, padding: 14, marginBottom: 10,
    cursor: 'pointer', border: '1px solid transparent', transition: 'border 0.15s',
  };
  const hover = (e: React.MouseEvent<HTMLDivElement>, on: boolean) => {
    e.currentTarget.style.borderColor = on ? '#a78bfa' : 'transparent';
  };

  return (
    <div style={overlay} onClick={onCancel}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ color: '#e2e8f0', fontSize: 18, fontWeight: 700, margin: 0, marginBottom: 8 }}>
          Already in Library
        </h2>
        <p style={{ color: '#94a3b8', fontSize: 13, marginBottom: 18 }}>
          <strong style={{ color: '#e2e8f0' }}>"{existingTitle}"</strong> is already
          tracked. What do you want to do?
        </p>

        <div
          style={optionRow}
          onMouseEnter={(e) => hover(e, true)}
          onMouseLeave={(e) => hover(e, false)}
          onClick={onKeepFiles}
        >
          <div style={{ color: '#a78bfa', fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
            Replace metadata · Keep files
          </div>
          <div style={{ color: '#94a3b8', fontSize: 12, lineHeight: 1.5 }}>
            Re-creates the library entry with the new title/schedule/metadata URL.
            Existing CBZ files in <code style={{ color: '#cbd5e1' }}>{existingFolder}</code> stay on disk.
          </div>
        </div>

        <div
          style={optionRow}
          onMouseEnter={(e) => hover(e, true)}
          onMouseLeave={(e) => hover(e, false)}
          onClick={onWipeFiles}
        >
          <div style={{ color: '#f87171', fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
            Wipe and start fresh
          </div>
          <div style={{ color: '#94a3b8', fontSize: 12, lineHeight: 1.5 }}>
            Deletes the entire <code style={{ color: '#fda4af' }}>{existingFolder}</code> folder
            and all its CBZs, then creates a brand new entry. Cannot be undone.
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 18 }}>
          <button onClick={onCancel}
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
