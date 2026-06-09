import React from 'react';
import { Link } from 'react-router-dom';
import { format, parseISO } from 'date-fns';

interface ReservationData {
  reservationId: string;
  confirmationNumber: string;
  propertyName: string;
  roomTypeName: string;
  checkInDate: string;
  checkOutDate: string;
  adults: number;
  children: number;
  totalAmount: number;
  currency: string;
  status: string;
}

interface BookingConfirmationProps {
  confirmationNumber: string;
  reservation: ReservationData;
}

const BookingConfirmation: React.FC<BookingConfirmationProps> = ({
  confirmationNumber,
  reservation,
}) => {
  const formatDate = (dateStr: string) => {
    try {
      return format(parseISO(dateStr), 'EEEE, MMMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  const totalGuests = reservation.adults + (reservation.children || 0);

  return (
    <div className="mx-auto max-w-2xl text-center">
      {/* Success icon */}
      <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-green-100">
        <svg className="h-10 w-10 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>

      {/* Heading */}
      <h1 className="mt-6 font-display text-3xl font-bold text-neutral-900">Booking Confirmed!</h1>
      <p className="mt-2 text-neutral-600">
        Your reservation has been successfully booked. A confirmation email has been sent to your email address.
      </p>

      {/* Confirmation number */}
      <div className="mt-6 rounded-xl bg-primary-50 px-6 py-4">
        <p className="text-sm font-medium text-primary-700">Confirmation Number</p>
        <p className="mt-1 font-display text-3xl font-bold tracking-wider text-primary-600">
          {confirmationNumber}
        </p>
      </div>

      {/* Reservation details card */}
      <div className="mt-8 rounded-xl border border-neutral-200 bg-white p-6 text-left shadow-sm">
        <h3 className="font-display text-lg font-semibold text-neutral-900">Reservation Details</h3>

        <div className="mt-4 space-y-3">
          <div className="flex justify-between border-b border-neutral-100 pb-3">
            <span className="text-sm text-neutral-500">Property</span>
            <span className="text-sm font-medium text-neutral-800">{reservation.propertyName}</span>
          </div>
          <div className="flex justify-between border-b border-neutral-100 pb-3">
            <span className="text-sm text-neutral-500">Room Type</span>
            <span className="text-sm font-medium text-neutral-800">{reservation.roomTypeName}</span>
          </div>
          <div className="flex justify-between border-b border-neutral-100 pb-3">
            <span className="text-sm text-neutral-500">Check-in</span>
            <span className="text-sm font-medium text-neutral-800">{formatDate(reservation.checkInDate)}</span>
          </div>
          <div className="flex justify-between border-b border-neutral-100 pb-3">
            <span className="text-sm text-neutral-500">Check-out</span>
            <span className="text-sm font-medium text-neutral-800">{formatDate(reservation.checkOutDate)}</span>
          </div>
          <div className="flex justify-between border-b border-neutral-100 pb-3">
            <span className="text-sm text-neutral-500">Guests</span>
            <span className="text-sm font-medium text-neutral-800">
              {reservation.adults} {reservation.adults === 1 ? 'Adult' : 'Adults'}
              {reservation.children > 0 &&
                `, ${reservation.children} ${reservation.children === 1 ? 'Child' : 'Children'}`}
              {' '}({totalGuests} total)
            </span>
          </div>
          <div className="flex justify-between pt-1">
            <span className="text-sm font-semibold text-neutral-700">Total</span>
            <span className="text-lg font-bold text-primary-600">
              ${reservation.totalAmount.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
        <Link
          to={`/account/reservations/${reservation.reservationId}`}
          className="inline-flex items-center justify-center rounded-lg bg-primary-600 px-6 py-3 text-sm font-semibold text-white hover:bg-primary-700 transition-colors"
        >
          View Reservation
        </Link>
        <Link
          to="/"
          className="inline-flex items-center justify-center rounded-lg border border-neutral-300 px-6 py-3 text-sm font-semibold text-neutral-700 hover:bg-neutral-50 transition-colors"
        >
          Book Another Stay
        </Link>
      </div>
    </div>
  );
};

export default BookingConfirmation;
