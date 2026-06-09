import React from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import * as reservationService from '../services/reservationService';
import BookingConfirmation from '../components/payment/BookingConfirmation';
import LoadingSpinner from '../components/common/LoadingSpinner';
import PublicLayout from '../components/layout/PublicLayout';

const ConfirmationPage: React.FC = () => {
  const { confirmationNumber } = useParams<{ confirmationNumber: string }>();
  const { user } = useAuth();

  const { data: reservations, isLoading } = useQuery({
    queryKey: ['reservations', user?.guestId],
    queryFn: () =>
      reservationService.getReservations({ guestId: user?.guestId }),
    enabled: !!confirmationNumber && !!user?.guestId,
  });

  // Find the matching reservation
  const reservation = reservations?.find(
    (r) => r.confirmationNumber === confirmationNumber
  );

  const handlePrint = () => {
    window.print();
  };

  return (
    <PublicLayout>
      <div className="mx-auto max-w-4xl px-4 py-16 sm:px-6 lg:px-8">
        {isLoading ? (
          <div className="flex justify-center py-20">
            <LoadingSpinner size="lg" message="Loading confirmation..." />
          </div>
        ) : reservation && confirmationNumber ? (
          <>
            <BookingConfirmation
              confirmationNumber={confirmationNumber}
              reservation={reservation}
            />

            {/* Print button */}
            <div className="mt-8 text-center print:hidden">
              <button
                type="button"
                onClick={handlePrint}
                className="inline-flex items-center gap-2 rounded-lg border border-neutral-300 px-6 py-2.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6.72 13.829c-.24.03-.48.062-.72.096m.72-.096a42.415 42.415 0 0110.56 0m-10.56 0L6.34 18m10.94-4.171c.24.03.48.062.72.096m-.72-.096L17.66 18m0 0l.229 2.523a1.125 1.125 0 01-1.12 1.227H7.231c-.662 0-1.18-.568-1.12-1.227L6.34 18m11.318 0h1.091A2.25 2.25 0 0021 15.75V9.456c0-1.081-.768-2.015-1.837-2.175a48.055 48.055 0 00-1.913-.247M6.34 18H5.25A2.25 2.25 0 013 15.75V9.456c0-1.081.768-2.015 1.837-2.175a48.041 48.041 0 011.913-.247m10.5 0a48.536 48.536 0 00-10.5 0m10.5 0V3.375c0-.621-.504-1.125-1.125-1.125h-8.25c-.621 0-1.125.504-1.125 1.125v3.659M18.75 12h.008v.008h-.008V12zm-3 0h.008v.008h-.008V12z" />
                </svg>
                Print Confirmation
              </button>
            </div>
          </>
        ) : (
          <div className="text-center py-20">
            <h2 className="font-display text-2xl font-bold text-neutral-800">
              Confirmation Not Found
            </h2>
            <p className="mt-2 text-neutral-500">
              We could not find a reservation with confirmation number {confirmationNumber}.
            </p>
          </div>
        )}
      </div>
    </PublicLayout>
  );
};

export default ConfirmationPage;
