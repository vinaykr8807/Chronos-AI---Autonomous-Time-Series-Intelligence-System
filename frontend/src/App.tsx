import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Footer, Navbar } from './components/layout';
import './App.css';

const Home = lazy(() => import('./pages/Home').then((module) => ({ default: module.Home })));
const Discover = lazy(() => import('./pages/Discover').then((module) => ({ default: module.Discover })));
const DatasetIntelligence = lazy(() => import('./pages/DatasetIntelligence').then((module) => ({ default: module.DatasetIntelligence })));
const PipelineStudio = lazy(() => import('./pages/PipelineStudio').then((module) => ({ default: module.PipelineStudio })));
const Forecast = lazy(() => import('./pages/Forecast').then((module) => ({ default: module.Forecast })));
const Monitor = lazy(() => import('./pages/Monitor').then((module) => ({ default: module.Monitor })));

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-space-900 text-slate-100">
        <Navbar />
        <main>
          <Suspense fallback={<div className="min-h-[60vh] px-6 py-10 text-sm text-slate-400">Loading workspace...</div>}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/discover" element={<Discover />} />
              <Route path="/dataset/:id" element={<DatasetIntelligence />} />
              <Route path="/pipeline" element={<PipelineStudio />} />
              <Route path="/forecast" element={<Forecast />} />
              <Route path="/monitor" element={<Monitor />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  );
}

export default App;
