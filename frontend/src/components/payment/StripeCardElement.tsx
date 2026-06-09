import React from 'react';
import { CardElement } from '@stripe/react-stripe-js';
import type { StripeCardElementChangeEvent } from '@stripe/stripe-js';

interface StripeCardElementProps {
  onChange?: (event: StripeCardElementChangeEvent) => void;
  error?: string | null;
}

const CARD_ELEMENT_OPTIONS = {
  style: {
    base: {
      fontSize: '14px',
      fontFamily: 'Inter, system-ui, sans-serif',
      color: '#1f2937',
      letterSpacing: '0.025em',
      '::placeholder': {
        color: '#9ca3af',
      },
    },
    invalid: {
      color: '#ef4444',
      iconColor: '#ef4444',
    },
  },
  hidePostalCode: false,
};

const StripeCardElement: React.FC<StripeCardElementProps> = ({ onChange, error }) => {
  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-neutral-700">Card Details</label>
      <div className="rounded-lg border border-neutral-300 bg-white px-4 py-3 transition-colors focus-within:border-primary-600 focus-within:ring-1 focus-within:ring-primary-600">
        <CardElement options={CARD_ELEMENT_OPTIONS} onChange={onChange} />
      </div>
      {error && (
        <p className="flex items-center gap-1.5 text-xs text-red-500">
          <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          {error}
        </p>
      )}
      <div className="flex items-center gap-2 text-xs text-neutral-400">
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
        </svg>
        <span>Your payment information is encrypted and secure</span>
      </div>
    </div>
  );
};

export default StripeCardElement;
