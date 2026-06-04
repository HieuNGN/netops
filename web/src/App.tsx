import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense, lazy } from 'react';
import { Header, PostSignupBanner } from './components/layout';
import { ToastProvider } from './components/ui/Toast';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { AuthProvider, useAuth } from './hooks/useAuth';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Topology = lazy(() => import('./pages/Topology'));
const TopologyHistory = lazy(() => import('./pages/TopologyHistory'));
const Devices = lazy(() => import('./pages/Devices'));
const ServiceChecks = lazy(() => import('./pages/ServiceChecks'));
const Alerts = lazy(() => import('./pages/Alerts'));
const Settings = lazy(() => import('./pages/Settings'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const NotFound = lazy(() => import('./pages/NotFound'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function ProtectedApp() {
  const { token, loading } = useAuth();
  const location = useLocation();
  const isAuthRoute = location.pathname === '/login';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="animate-spin rounded-sm h-8 w-8 border-b-2 border-ring" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white dark:bg-black text-foreground">
      {!isAuthRoute && <Header />}
      {!isAuthRoute && <PostSignupBanner />}
      <Suspense fallback={
        <div className="flex items-center justify-center h-[calc(100vh-4rem)] bg-background">
          <div className="animate-spin rounded-sm h-8 w-8 border-b-2 border-ring" />
        </div>
      }>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={token ? <Dashboard /> : <Navigate to="/login" replace />} />
          <Route path="/topology" element={token ? <Topology /> : <Navigate to="/login" replace />} />
          <Route path="/topology/history" element={token ? <TopologyHistory /> : <Navigate to="/login" replace />} />
          <Route path="/devices" element={token ? <Devices /> : <Navigate to="/login" replace />} />
          <Route path="/checks" element={token ? <ServiceChecks /> : <Navigate to="/login" replace />} />
          <Route path="/alerts" element={token ? <Alerts /> : <Navigate to="/login" replace />} />
          <Route path="/settings" element={token ? <Settings /> : <Navigate to="/login" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <AuthProvider>
              <ProtectedApp />
            </AuthProvider>
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
