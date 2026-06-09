import React, { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { format, parseISO, isBefore } from 'date-fns';
import { useAuth } from '../../context/AuthContext';
import * as reservationService from '../../services/reservationService';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import PublicLayout from '../../components/layout/PublicLayout';

type StatusTab = 'all' | 'upcoming' | 'past' | 'cancelled';

const STATUS_COLORS: Record<string, string> = {
  CONFIRMED: 'bg-green-100 text-green-700',
  CHECKED_IN: 'bg-blue-100 text-blue-700',
  CHECKED_OUT: 'bg-neutral-100 text-neutral-600',
  CANCELLED: 'bg-red-100 text-red-600',
  NO_SHOW: 'bg-orange-100 text-orange-700',
};

const formatStatus = (status: string): string => {
  return status
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
};

const ReservationsPage: React.FC = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<StatusTab>('all');

  const { data: reservations, isLoading } = useQuery({
    queryKey: ['reservations', user?.guestId],
    queryFn: () =>
      reservationService.getReservations({
        guestId: user?.guestId,
      }),
    enabled: !!user?.guestId,
    staleTime: 0,
  });

  const filteredReservations = useMemo(() => {
    if (!reservations) return [];
    const now = new Date();

    switch (activeTab) {
      case 'upcoming':
        return reservations.filter(
          (r) =>
            r.status !== 'CANCELLED' &&
            !isBefore(parseISO(r.checkInDate), now)
        );
      case 'past':
        return reservations.filter(
          (r) =>
            r.status !== 'CANCELLED' &&
            isBefore(parseISO(r.checkOutDate), now)
        );
      case 'cancelled':
        return reservations.filter((r) => r.status === 'CANCELLED');
      default:
        return reservations;
    }
  }, [reservations, activeTab]);

  const tabs: { key: StatusTab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'upcoming', label: 'Upcoming' },
    { key: 'past', label: 'Past' },
    { key: 'cancelled', label: 'Cancelled' },
  ];

  const formatDate = (dateStr: string) => {
    try {
      return format(parseISO(dateStr), 'MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  return (
    <PublicLayout>
      <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          <h1 className="font-display text-3xl font-bold text-neutral-900">My Reservations</h1>
          <Link
            to="/"
            className="rounded-lg bg-primary-600 px-5 py-2 text-sm font-semibold text-white hover:bg-primary-700 transition-colors"
          >
            Book New Stay
          </Link>
        </div>

        {/* Tabs */}
        <div className="mt-6 flex gap-1 rounded-lg bg-neutral-100 p-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-white text-primary-600 shadow-sm'
                  : 'text-neutral-500 hover:text-neutral-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Reservation list */}
        <div className="mt-6">
          {isLoading ? (
            <div className="flex justify-center py-16">
              <LoadingSpinner message="Loading reservations..." />
            </div>
          ) : filteredReservations.length > 0 ? (
            <div className="space-y-4">
              {filteredReservations.map((reservation) => (
                <Link
                  key={reservation.reservationId}
                  to={`/account/reservations/${reservation.reservationId}`}
                  className="block rounded-xl border border-neutral-200 bg-white p-5 shadow-sm hover:border-primary-300 hover:shadow-md transition-all"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <h3 className="font-display text-base font-semibold text-neutral-900">
                          {reservation.propertyName}
                        </h3>
                        <span
                          className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                            STATUS_COLORS[reservation.status] ?? 'bg-neutral-100 text-neutral-600'
                          }`}
                        >
                          {formatStatus(reservation.status)}
                        </span>
                      </div>

                      <p className="mt-1 text-sm text-neutral-500">{reservation.roomTypeName}</p>

                      <div className="mt-2 flex flex-wrap gap-4 text-sm text-neutral-600">
                        <span className="flex items-center gap-1.5">
                          <svg className="h-4 w-4 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                          </svg>
                          {formatDate(reservation.checkInDate)} - {formatDate(reservation.checkOutDate)}
                        </span>
                        <span className="font-mono text-xs text-neutral-400">
                          #{reservation.confirmationNumber}
                        </span>
                      </div>
                    </div>

                    <div className="text-right">
                      <p className="text-lg font-bold text-primary-600">
                        ${(reservation.totalAmount ?? 0).toFixed(2)}
                      </p>
                      <p className="text-xs text-neutral-400">{reservation.currency ?? 'USD'}</p>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-neutral-200 bg-white py-16 text-center">
              <svg
                className="mx-auto h-12 w-12 text-neutral-300"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"
                />
              </svg>
              <h3 className="mt-4 font-display text-lg font-semibold text-neutral-700">
                No reservations found
              </h3>
              <p className="mt-1 text-sm text-neutral-500">
                {activeTab === 'all'
                  ? "You haven't made any reservations yet."
                  : `No ${activeTab} reservations.`}
              </p>
              <Link
                to="/"
                className="mt-6 inline-block rounded-lg bg-primary-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 transition-colors"
              >
                Book Your First Stay
              </Link>
            </div>
          )}
        </div>
      </div>
    </PublicLayout>
  );
};

export default ReservationsPage;
