import { useState, useEffect } from 'react';
import { api } from '../api';
import type { AppSettings } from '../types';

const SCHEDULE_OPTIONS = [
  { label: 'Never', value: 0 },
  { label: 'Every 6 hours', value: 21600 },
  { label: 'Every 12 hours', value: 43200 },
  { label: 'Daily', value: 86400 },
  { label: 'Weekly', value: 604800 },
];

const labelStyle: React.CSSProperties = {
  display: 'block',
  color: '#64748b',
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  background: '#0f172a',
  border: '1px solid #334155',
  borderRadius: 6,
  color: '#e2e8f0',
  fontSize: 13,
  padding: '8px 12px',
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box',
};

const readonlyStyle: React.CSSProperties = {
  ...inputStyle,
  color: '#64748b',
  cursor: 'not-allowed',
};

const fieldWrap: React.CSSProperties = {
  marginBottom: 20,
};

export default function Settings() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Editable fields
  const [concurrentDownloads, setConcurrentDownloads] = useState(3);
  const [metaAutoLookup, setMetaAutoLookup] = useState(false);
  const [defaultInterval, setDefaultInterval] = useState(0);
  const [komgaUrl, setKomgaUrl] = useState('');
  const [komgaApiKey, setKomgaApiKey] = useState('');

  useEffect(() => {
    api.getSettings()
      .then((s) => {
        setSettings(s);
        setConcurrentDownloads(s.concurrent_downloads);
        setMetaAutoLookup(s.metadata_auto_lookup);
        setDefaultInterval(s.default_schedule_interval);
        setKomgaUrl(s.komga_url || '');
      })
      .catch(() => setError('Failed to load settings'))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    setSaveMsg(null);
    try {
      const payload: Record<string, unknown> = {
        concurrent_downloads: concurrentDownloads,
        metadata_auto_lookup: metaAutoLookup,
        default_schedule_interval: defaultInterval,
        komga_url: komgaUrl,
      };
      // Only send the API key if the user typed a new one
      if (komgaApiKey.trim()) payload.komga_api_key = komgaApiKey.trim();
      const fresh = await api.updateSettings(payload);
      setSettings(fresh);
      setKomgaApiKey('');  // clear the input once saved
      setSaveMsg('Settings saved successfully.');
      setTimeout(() => setSaveMsg(null), 3000);
    } catch {
      setSaveMsg('Failed to save settings.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div style={{ color: '#64748b', padding: 20 }}>Loading...</div>;
  if (error || !settings) return <div style={{ color: '#ef4444', padding: 20 }}>{error ?? 'Error'}</div>;

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: 22, fontWeight: 700, marginBottom: 24, marginTop: 4 }}>
        Settings
      </h1>

      <div style={{ background: '#1e293b', borderRadius: 8, padding: 24, marginBottom: 20 }}>
        {/* Library paths — read-only, configured via env vars */}
        <div style={fieldWrap}>
          <label style={labelStyle}>Default Library Path</label>
          <input style={readonlyStyle} value={settings.library_path} readOnly />
          <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
            Used when a per-content-type path isn't set. Configured via
            <code style={{ color: '#94a3b8' }}> READEX_LIBRARY_PATH</code>.
          </div>
        </div>

        <div style={fieldWrap}>
          <label style={labelStyle}>Manga Path</label>
          <input style={readonlyStyle}
            value={settings.manga_path || '(uses default library path)'} readOnly />
          <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
            <code style={{ color: '#94a3b8' }}>READEX_MANGA_PATH</code>
          </div>
        </div>

        <div style={fieldWrap}>
          <label style={labelStyle}>Manhwa Path</label>
          <input style={readonlyStyle}
            value={settings.manhwa_path || '(uses default library path)'} readOnly />
          <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
            <code style={{ color: '#94a3b8' }}>READEX_MANHWA_PATH</code>
          </div>
        </div>

        <div style={fieldWrap}>
          <label style={labelStyle}>Comic Path</label>
          <input style={readonlyStyle}
            value={settings.comic_path || '(uses default library path)'} readOnly />
          <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
            <code style={{ color: '#94a3b8' }}>READEX_COMIC_PATH</code> · restart Readex after changing
          </div>
        </div>

        {/* Concurrent Downloads */}
        <div style={fieldWrap}>
          <label style={labelStyle}>Concurrent Downloads</label>
          <input
            style={{ ...inputStyle, width: 100 }}
            type="number"
            min={1}
            max={10}
            value={concurrentDownloads}
            onChange={(e) => setConcurrentDownloads(Math.max(1, Math.min(10, Number(e.target.value))))}
          />
        </div>

        {/* Metadata Auto-Lookup */}
        <div style={{ ...fieldWrap, display: 'flex', alignItems: 'center', gap: 12 }}>
          <input
            type="checkbox"
            id="meta-auto"
            checked={metaAutoLookup}
            onChange={(e) => setMetaAutoLookup(e.target.checked)}
            style={{ accentColor: '#a78bfa', width: 16, height: 16 }}
          />
          <label htmlFor="meta-auto" style={{ color: '#e2e8f0', fontSize: 13, cursor: 'pointer' }}>
            Metadata Auto-Lookup
            <span style={{ display: 'block', color: '#64748b', fontSize: 11, marginTop: 2 }}>
              Automatically fetch metadata when adding new series
            </span>
          </label>
        </div>

        {/* Default Schedule Interval */}
        <div style={fieldWrap}>
          <label style={labelStyle}>Default Schedule Interval</label>
          <select
            style={{ ...inputStyle, cursor: 'pointer' }}
            value={defaultInterval}
            onChange={(e) => setDefaultInterval(Number(e.target.value))}
          >
            {SCHEDULE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {/* Bulk maintenance actions */}
        <div style={fieldWrap}>
          <label style={labelStyle}>Maintenance</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              onClick={async () => {
                if (!window.confirm('Start a background metadata sync for every series? Watch progress on the Library page (top of the grid). It survives reload / navigation.')) return;
                try {
                  const r = await api.startMetadataSync();
                  alert(r.message ?? 'Sync started — open the Library page to see progress.');
                } catch (e) {
                  alert('Failed to start sync: ' + (e as Error).message);
                }
              }}
              style={{
                background: '#a78bfa', border: 'none', borderRadius: 6,
                color: '#0f172a', fontSize: 13, fontWeight: 700,
                padding: '8px 16px', cursor: 'pointer',
              }}
            >
              Re-sync All Metadata
            </button>
          </div>
          <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
            Refreshes status (ongoing/complete/etc), cover image, and series.json
            for every series. Useful after importing.
          </div>
        </div>

        {/* Komga integration */}
        <div style={fieldWrap}>
          <label style={labelStyle}>Komga URL</label>
          <input
            style={inputStyle}
            placeholder="http://komga:25600"
            value={komgaUrl}
            onChange={(e) => setKomgaUrl(e.target.value)}
          />
          <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
            Used to trigger library rescans after metadata writes.
          </div>
        </div>

        <div style={fieldWrap}>
          <label style={labelStyle}>Komga API Key</label>
          <input
            style={inputStyle}
            type="password"
            placeholder={settings.komga_api_key_set ? '••••••••••••••••••••••••••••••••' : 'paste API key from Komga → Account Settings → API Keys'}
            value={komgaApiKey}
            onChange={(e) => setKomgaApiKey(e.target.value)}
          />
          <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
            {settings.komga_api_key_set
              ? 'Key is set. Leave blank to keep current; type a new value to replace.'
              : 'Paste a key here to enable auto-rescan.'}
          </div>
        </div>

        {/* Sources — read-only */}
        <div style={fieldWrap}>
          <label style={labelStyle}>Registered Sources</label>
          {settings.sources.length === 0 ? (
            <div style={{ color: '#475569', fontSize: 13 }}>No sources registered</div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {settings.sources.map((s) => (
                <span
                  key={s}
                  style={{
                    background: '#166534',
                    color: '#4ade80',
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '3px 10px',
                    borderRadius: 12,
                    letterSpacing: '0.04em',
                  }}
                >
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {saveMsg && (
        <div style={{
          background: saveMsg.includes('Failed') ? '#450a0a' : '#14532d',
          color: saveMsg.includes('Failed') ? '#fca5a5' : '#4ade80',
          borderRadius: 6,
          padding: '10px 16px',
          fontSize: 13,
          marginBottom: 16,
        }}>
          {saveMsg}
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        style={{
          background: '#a78bfa',
          border: 'none',
          borderRadius: 6,
          color: '#0f172a',
          fontSize: 14,
          fontWeight: 700,
          padding: '10px 28px',
          cursor: saving ? 'not-allowed' : 'pointer',
          opacity: saving ? 0.7 : 1,
        }}
      >
        {saving ? 'Saving...' : 'Save'}
      </button>
    </div>
  );
}
