import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import LoadingSpinner from './components/LoadingSpinner';
import SignInPage from './pages/SignInPage';

// Lazy-loaded pages
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const StaysPage = lazy(() => import('./pages/StaysPage'));
const CheckInPage = lazy(() => import('./pages/CheckInPage'));
const HousekeepingPage = lazy(() => import('./pages/HousekeepingPage'));
const BillingPage = lazy(() => import('./pages/BillingPage'));
const FolioDetailPage = lazy(() => import('./pages/FolioDetailPage'));
const GuestsPage = lazy(() => import('./pages/GuestsPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
const AuditPage = lazy(() => import('./pages/AuditPage'));

function App() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner fullScreen />;
  }

  if (!isAuthenticated) {
    return <SignInPage />;
  }

  return (
    <Layout>
      <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/stays" element={<StaysPage />} />
          <Route path="/stays/:reservationId/checkin" element={<CheckInPage />} />
          <Route path="/housekeeping" element={<HousekeepingPage />} />
          <Route path="/billing" element={<BillingPage />} />
          <Route path="/billing/:folioId" element={<FolioDetailPage />} />
          <Route path="/guests" element={<GuestsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}

export default App;
