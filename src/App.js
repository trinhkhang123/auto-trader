import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Dashboard from './pages/Dashboard';
import TradeDetail from './pages/TradeDetail';
import Navbar from './components/Navbar';
import { TradeProvider } from './context/TradeContext';

function App() {
  return (
    <TradeProvider>
      <Router>
        <div className="min-h-screen bg-gray-100">
          <Navbar />
          <main className="container mx-auto px-4 py-6">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/trade/:id" element={<TradeDetail />} />
            </Routes>
          </main>
          <Toaster position="top-right" />
        </div>
      </Router>
    </TradeProvider>
  );
}

export default App;
