import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, parseISO, differenceInCalendarDays } from 'date-fns';
import * as reservationService from '../../services/reservationService';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import PublicLayout from '../../components/layout/PublicLayout';

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  CONFIRMED: { bg: 'bg-green-100', text: 'text-green-700', label: 'Confirmed' },
  CHECKED_IN: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Checked In' },
  CHECKED_OUT: { bg: 'bg-neutral-100', text: 'text-neutral-600', label: 'Checked Out' },
  CANCELLED: { bg: 'bg-red-100', text: 'text-red-600', label: 'Cancelled' },
  NO_SHOW: { bg: 'bg-orange-100', text: 'text-orange-700', label: 'No Show' },
};

const ReservationDetailPage: React.FC = () => {
  const { reservationId } = useParams<{ reservationId: string }>();
  const queryClient = useQueryClient();

  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState('');

  const { data: reservation, isLoading } = useQuery({
    queryKey: ['reservation', reservationId],
    queryFn: () => reservationService.getReservation(reservationId!),
    enabled: !!reservationId,
  });

  const cancelMutation = useMutation({
    mutationFn: () =>
      reservationService.cancelReservation(reservationId!, cancelReason || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reservation', reservationId] });
      queryClient.invalidateQueries({ queryKey: ['reservations'] });
      setShowCancelModal(false);
    },
  });

  const formatDate = (dateStr: string) => {
    try {
      return format(parseISO(dateStr), 'EEEE, MMMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  if (isLoading) {
    return (
      <PublicLayout>
        <div className="flex min-h-[60vh] items-center justify-center">
          <LoadingSpinner size="lg" message="Loading reservation..." />
        </div>
      </PublicLayout>
    );
  }

  if (!reservation) {
    return (
      <PublicLayout>
        <div className="flex min-h-[60vh] flex-col items-center justify-center">
          <h2 className="font-display text-2xl font-bold text-neutral-800">
            Reservation Not Found
          </h2>
          <p className="mt-2 text-neutral-500">
            The reservation you are looking for does not exist.
          </p>
          <Link
            to="/account/reservations"
            className="mt-6 rounded-lg bg-primary-600 px-6 py-2 text-sm font-semibold text-white hover:bg-primary-700 transition-colors"
          >
            Back to Reservations
          </Link>
        </div>
      </PublicLayout>
    );
  }

  const nights = differenceInCalendarDays(
    parseISO(reservation.checkOutDate),
    parseISO(reservation.checkInDate)
  );

  const statusInfo = STATUS_BADGE[reservation.status] ?? {
    bg: 'bg-neutral-100',
    text: 'text-neutral-600',
    label: reservation.status,
  };

  const canCancel = reservation.status === 'CONFIRMED';
  const TAX_RATE = 0.12;
  const totalAmount = reservation.totalAmount ?? 0;
  const estimatedSubtotal = totalAmount / (1 + TAX_RATE);
  const estimatedTax = totalAmount - estimatedSubtotal;

  return (
    <PublicLayout>
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
        {/* Back link */}
        <Link
          to="/account/reservations"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:text-primary-700"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
          Back to Reservations
        </Link>

        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="font-display text-3xl font-bold text-neutral-900">
              Reservation Details
            </h1>
            <p className="mt-1 font-mono text-sm text-neutral-500">
              Confirmation #{reservation.confirmationNumber}
            </p>
          </div>
          <span
            className={`inline-block self-start rounded-full px-4 py-1.5 text-sm font-semibold ${statusInfo.bg} ${statusInfo.text}`}
          >
            {statusInfo.label}
          </span>
        </div>

        {/* Details card */}
        <div className="mt-8 rounded-xl border border-neutral-200 bg-white shadow-xs">
          {/* Property & Room */}
          <div className="border-b border-neutral-100 p-6">
            <h2 className="font-display text-xl font-semibold text-neutral-900">
              {reservation.propertyName}
            </h2>
            <p className="mt-1 text-sm text-neutral-500">{reservation.roomTypeName}</p>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-6 border-b border-neutral-100 p-6">
            <div>
              <p className="text-xs font-medium text-neutral-500">Check-in</p>
              <p className="mt-1 text-sm font-medium text-neutral-800">
                {formatDate(reservation.checkInDate)}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-neutral-500">Check-out</p>
              <p className="mt-1 text-sm font-medium text-neutral-800">
                {formatDate(reservation.checkOutDate)}
              </p>
            </div>
          </div>

          {/* Guests & Stay info */}
          <div className="grid grid-cols-2 gap-6 border-b border-neutral-100 p-6">
            <div>
              <p className="text-xs font-medium text-neutral-500">Duration</p>
              <p className="mt-1 text-sm font-medium text-neutral-800">
                {nights} {nights === 1 ? 'night' : 'nights'}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-neutral-500">Guests</p>
              <p className="mt-1 text-sm font-medium text-neutral-800">
                {reservation.adults} {reservation.adults === 1 ? 'Adult' : 'Adults'}
                {reservation.children > 0 &&
                  `, ${reservation.children} ${reservation.children === 1 ? 'Child' : 'Children'}`}
              </p>
            </div>
          </div>

          {/* Special requests */}
          {reservation.specialRequests && (
            <div className="border-b border-neutral-100 p-6">
              <p className="text-xs font-medium text-neutral-500">Special Requests</p>
              <p className="mt-1 text-sm text-neutral-800">{reservation.specialRequests}</p>
            </div>
          )}

          {/* Pricing breakdown */}
          <div className="p-6">
            <h3 className="text-sm font-semibold text-neutral-800">Pricing</h3>
            <div className="mt-3 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-neutral-600">Room charges</span>
                <span className="font-medium text-neutral-800">
                  ${estimatedSubtotal.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-neutral-600">Taxes & fees</span>
                <span className="font-medium text-neutral-800">
                  ${estimatedTax.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between border-t border-neutral-200 pt-2">
                <span className="text-base font-semibold text-neutral-900">Total</span>
                <span className="text-xl font-bold text-primary-600">
                  ${totalAmount.toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Cancel button */}
        {canCancel && (
          <div className="mt-8 text-center">
            <button
              type="button"
              onClick={() => setShowCancelModal(true)}
              className="rounded-lg border border-red-300 px-6 py-2.5 text-sm font-semibold text-red-600 hover:bg-red-50 transition-colors"
            >
              Cancel Reservation
            </button>
          </div>
        )}
      </div>

      {/* Cancel confirmation modal */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
            <h3 className="font-display text-lg font-semibold text-neutral-900">
              Cancel Reservation?
            </h3>
            <p className="mt-2 text-sm text-neutral-600">
              Are you sure you want to cancel this reservation? This action cannot be undone.
              Cancellation fees may apply per the rate plan policy.
            </p>

            <div className="mt-4">
              <label className="mb-1 block text-sm font-medium text-neutral-700">
                Reason (optional)
              </label>
              <textarea
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-neutral-300 px-3 py-2 text-sm text-neutral-800 focus:border-primary-600 focus:outline-hidden focus:ring-1 focus:ring-primary-600 resize-none"
                placeholder="e.g., Change of plans"
              />
            </div>

            {cancelMutation.isError && (
              <p className="mt-3 text-sm text-red-500">
                Cancellation failed. Please try again or contact support.
              </p>
            )}

            <div className="mt-6 flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => setShowCancelModal(false)}
                disabled={cancelMutation.isPending}
                className="rounded-lg border border-neutral-300 px-5 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 transition-colors"
              >
                Keep Reservation
              </button>
              <button
                type="button"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
                className="rounded-lg bg-red-600 px-5 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60 transition-colors"
              >
                {cancelMutation.isPending ? 'Cancelling...' : 'Yes, Cancel'}
              </button>
            </div>
          </div>
        </div>
      )}
    </PublicLayout>
  );
};

export default ReservationDetailPage;
