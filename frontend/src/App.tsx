import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import Search from './pages/Search';
import SeriesDetail from './pages/SeriesDetail';
import Settings from './pages/Settings';
import Import from './pages/Import';
import Queue from './pages/Queue';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/library" element={<Library />} />
        <Route path="/search" element={<Search />} />
        <Route path="/import" element={<Import />} />
        <Route path="/queue" element={<Queue />} />
        <Route path="/series/:id" element={<SeriesDetail />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Layout>
  );
}
