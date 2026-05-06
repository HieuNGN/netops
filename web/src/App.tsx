import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense, lazy } from 'react';
import { Header } from './components/layout';
import { ToastProvider } from './components/ui/Toast';
import { ErrorBoundary } from './components/ErrorBoundary';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Topology = lazy(() => import('./pages/Topology'));
const Devices = lazy(() => import('./pages/Devices'));
const ServiceChecks = lazy(() => import('./pages/ServiceChecks'));
const Alerts = lazy(() => import('./pages/Alerts'));
const Settings = lazy(() => import('./pages/Settings'));
const NotFound = lazy(() => import('./pages/NotFound'));

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
              <Suspense fallback={
                <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
                  <div className="animate-spin rounded-sm h-8 w-8 border-b-2 border-[#da1e28]" />
                </div>
              }>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/topology" element={<Topology />} />
                  <Route path="/devices" element={<Devices />} />
                  <Route path="/checks" element={<ServiceChecks />} />
                  <Route path="/alerts" element={<Alerts />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </div>
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
