import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Header } from './components/layout';
import { ToastProvider } from './components/ui/Toast';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Dashboard } from './pages/Dashboard';
import { Topology } from './pages/Topology';
import { Devices } from './pages/Devices';
import { ServiceChecks } from './pages/ServiceChecks';
import { Alerts } from './pages/Alerts';
import { Settings } from './pages/Settings';
import { NotFound } from './pages/NotFound';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <div className="min-h-screen bg-white dark:bg-black text-[#161616] dark:text-[#f4f4f4]">
              <Header />
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/topology" element={<Topology />} />
                <Route path="/devices" element={<Devices />} />
                <Route path="/checks" element={<ServiceChecks />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </div>
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
