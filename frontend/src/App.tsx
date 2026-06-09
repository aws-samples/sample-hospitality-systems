import React, { lazy, Suspense } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

// Lazy-loaded page components
const HomePage = lazy(() => import('@/pages/HomePage'));
const SearchResultsPage = lazy(() => import('@/pages/SearchResultsPage'));
const PropertyDetailPage = lazy(() => import('@/pages/PropertyDetailPage'));
const BookingPage = lazy(() => import('@/pages/BookingPage'));
const ConfirmationPage = lazy(() => import('@/pages/ConfirmationPage'));
const SignInPage = lazy(() => import('@/pages/auth/SignInPage'));
const AccountPage = lazy(() => import('@/pages/account/AccountPage'));
const ReservationsPage = lazy(() => import('@/pages/account/ReservationsPage'));
const ReservationDetailPage = lazy(() => import('@/pages/account/ReservationDetailPage'));

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
    </div>
  );
}

interface ProtectedRouteProps {
  children: React.ReactNode;
}

function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingFallback />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/signin" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/search" element={<SearchResultsPage />} />
        <Route path="/properties" element={<Navigate to="/search" replace />} />
        <Route path="/properties/:propertyId" element={<PropertyDetailPage />} />
        <Route path="/booking/:cartId" element={<BookingPage />} />
        <Route path="/confirmation/:confirmationNumber" element={<ConfirmationPage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route
          path="/account"
          element={
            <ProtectedRoute>
              <AccountPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account/reservations"
          element={
            <ProtectedRoute>
              <ReservationsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account/reservations/:reservationId"
          element={
            <ProtectedRoute>
              <ReservationDetailPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </Suspense>
  );
}
