import React from 'react';
import { differenceInCalendarDays, parseISO, format } from 'date-fns';

interface BookingSummaryProps {
  cart: {
    property: {
      name: string;
    };
    roomType: {
      name: string;
    };
    dates: {
      checkIn: string;
      checkOut: string;
    };
    pricing: {
      nightlyRate: number;
      numberOfNights: number;
      subtotal: number;
      taxes: number;
      fees: number;
      total: number;
      currency: string;
    };
    promoCode?: string | null;
    discountAmount?: number;
  };
}

const BookingSummary: React.FC<BookingSummaryProps> = ({ cart }) => {
  const { property, roomType, dates, pricing, promoCode, discountAmount } = cart;

  const nights =
    pricing.numberOfNights ||
    differenceInCalendarDays(parseISO(dates.checkOut), parseISO(dates.checkIn));

  const formatDate = (dateStr: string) => {
    try {
      return format(parseISO(dateStr), 'EEE, MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  const taxAmount = pricing.taxes > 0 ? pricing.taxes : pricing.subtotal * 0.12;
  const discount = discountAmount ?? 0;
  const displayTotal = pricing.total > 0 ? pricing.total : pricing.subtotal + taxAmount - discount;

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-6 shadow-xs">
      <h3 className="font-display text-lg font-semibold text-neutral-900">Booking Summary</h3>

      {/* Property and room */}
      <div className="mt-4 space-y-1.5">
        <p className="text-sm font-medium text-neutral-800">{property.name}</p>
        <p className="text-sm text-neutral-500">{roomType.name}</p>
      </div>

      {/* Dates */}
      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-neutral-100 pt-4">
        <div>
          <p className="text-xs font-medium text-neutral-500">Check-in</p>
          <p className="mt-0.5 text-sm font-medium text-neutral-800">{formatDate(dates.checkIn)}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-neutral-500">Check-out</p>
          <p className="mt-0.5 text-sm font-medium text-neutral-800">{formatDate(dates.checkOut)}</p>
        </div>
      </div>

      <p className="mt-2 text-xs text-neutral-400">
        {nights} {nights === 1 ? 'night' : 'nights'}
      </p>

      {/* Pricing breakdown */}
      <div className="mt-4 space-y-2 border-t border-neutral-100 pt-4">
        <div className="flex justify-between text-sm">
          <span className="text-neutral-600">
            ${pricing.nightlyRate.toFixed(2)} x {nights} {nights === 1 ? 'night' : 'nights'}
          </span>
          <span className="font-medium text-neutral-800">
            ${pricing.subtotal.toFixed(2)}
          </span>
        </div>

        <div className="flex justify-between text-sm">
          <span className="text-neutral-600">Taxes & fees (12%)</span>
          <span className="font-medium text-neutral-800">${taxAmount.toFixed(2)}</span>
        </div>

        {discount > 0 && promoCode && (
          <div className="flex justify-between text-sm">
            <span className="text-green-600">
              Discount ({promoCode})
            </span>
            <span className="font-medium text-green-600">-${discount.toFixed(2)}</span>
          </div>
        )}
      </div>

      {/* Total */}
      <div className="mt-4 flex justify-between border-t border-neutral-200 pt-4">
        <span className="text-base font-semibold text-neutral-900">Total</span>
        <span className="text-xl font-bold text-primary-600">${displayTotal.toFixed(2)}</span>
      </div>
    </div>
  );
};

export default BookingSummary;
