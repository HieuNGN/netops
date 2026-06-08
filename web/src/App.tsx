import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense, lazy, useCallback, useState } from 'react';
import { Header, PostSignupBanner } from './components/layout';
import { ToastProvider } from './components/ui/Toast';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { AuthProvider, useAuth } from './hooks/useAuth';
import {
  useDeviceEvents,
  type ProfileGuessedEvent,
  type NetworkChangedEvent,
} from './hooks/useDeviceEvents';
import {
  ProfileConfirmModal,
  type EnvironmentProfileName,
} from './components/ProfileConfirmModal';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Topology = lazy(() => import('./pages/Topology'));
const TopologyHistory = lazy(() => import('./pages/TopologyHistory'));
const Devices = lazy(() => import('./pages/Devices'));
const DeviceDetail = lazy(() => import('./pages/DeviceDetail'));
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
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();
  const isAuthRoute = location.pathname === '/login';

  const [pendingGuess, setPendingGuess] = useState<{
    profile: EnvironmentProfileName;
    deviceCount: number;
    source: 'startup' | 'runtime' | 'manual';
  } | null>(null);

  const handleProfileGuessed = useCallback((e: ProfileGuessedEvent) => {
    if (e.confirmed) return;
    setPendingGuess({
      profile: e.profile,
      deviceCount: e.device_count,
      source: 'runtime',
    });
  }, []);

  const handleNetworkChanged = useCallback((e: NetworkChangedEvent) => {
    if (e.source === 'watcher') {
      setPendingGuess(null);
    }
  }, []);

  useDeviceEvents({
    onProfileGuessed: handleProfileGuessed,
    onNetworkChanged: handleNetworkChanged,
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="animate-spin rounded-sm h-8 w-8 border-b-2 border-ring" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      {!isAuthRoute && <Header />}
      {!isAuthRoute && <PostSignupBanner />}
      <Suspense fallback={
        <div className="flex items-center justify-center h-[calc(100vh-4rem)] bg-background">
          <div className="animate-spin rounded-sm h-8 w-8 border-b-2 border-ring" />
        </div>
      }>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={isAuthenticated ? <Dashboard /> : <Navigate to="/login" replace />} />
          <Route path="/topology" element={isAuthenticated ? <Topology /> : <Navigate to="/login" replace />} />
          <Route path="/topology/history" element={isAuthenticated ? <TopologyHistory /> : <Navigate to="/login" replace />} />
          <Route path="/devices" element={isAuthenticated ? <Devices /> : <Navigate to="/login" replace />} />
          <Route path="/devices/:id" element={isAuthenticated ? <DeviceDetail /> : <Navigate to="/login" replace />} />
          <Route path="/checks" element={isAuthenticated ? <ServiceChecks /> : <Navigate to="/login" replace />} />
          <Route path="/alerts" element={isAuthenticated ? <Alerts /> : <Navigate to="/login" replace />} />
          <Route path="/settings" element={isAuthenticated ? <Settings /> : <Navigate to="/login" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
      {pendingGuess && (
        <ProfileConfirmModal
          open={!!pendingGuess}
          detectedProfile={pendingGuess.profile}
          deviceCount={pendingGuess.deviceCount}
          source={pendingGuess.source}
          onDismiss={() => setPendingGuess(null)}
          onConfirmed={() => setPendingGuess(null)}
        />
      )}
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
