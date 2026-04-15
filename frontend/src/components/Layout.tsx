import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';

const navStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '12px 20px', borderBottom: '1px solid #334155', background: '#0f172a',
};
const linkBase: React.CSSProperties = { color: '#64748b', fontSize: 13, textDecoration: 'none' };
const linkActive: React.CSSProperties = { ...linkBase, color: '#e2e8f0', fontWeight: 600, borderBottom: '2px solid #a78bfa', paddingBottom: 2 };

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', background: '#0f172a' }}>
      <nav style={navStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <img src="/readex.png" alt="Readex" style={{ height: 22, width: 'auto', display: 'block' }} />
          <span style={{ fontSize: 18, fontWeight: 700, color: '#a78bfa', letterSpacing: '0.02em' }}>Readex</span>
          <span style={{ color: '#475569' }}>|</span>
          <NavLink to="/" end style={({ isActive }) => isActive ? linkActive : linkBase}>Dashboard</NavLink>
          <NavLink to="/library" style={({ isActive }) => isActive ? linkActive : linkBase}>Library</NavLink>
          <NavLink to="/search" style={({ isActive }) => isActive ? linkActive : linkBase}>Search</NavLink>
          <NavLink to="/queue" style={({ isActive }) => isActive ? linkActive : linkBase}>Queue</NavLink>
          <NavLink to="/import" style={({ isActive }) => isActive ? linkActive : linkBase}>Import</NavLink>
          <NavLink to="/settings" style={({ isActive }) => isActive ? linkActive : linkBase}>Settings</NavLink>
        </div>
      </nav>
      <main style={{ padding: 20 }}>{children}</main>
    </div>
  );
}
