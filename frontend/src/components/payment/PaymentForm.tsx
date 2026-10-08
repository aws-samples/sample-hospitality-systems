import React, { useState } from 'react';
import { useStripe, useElements, CardElement } from '@stripe/react-stripe-js';
import type { StripeCardElementChangeEvent } from '@stripe/stripe-js';
import StripeCardElement from './StripeCardElement';

interface PaymentFormProps {
  amount: number;
  clientSecret: string;
  onPaymentComplete: (paymentIntentId: string) => void;
  isLoading?: boolean;
}

const PaymentForm: React.FC<PaymentFormProps> = ({
  amount,
  clientSecret,
  onPaymentComplete,
  isLoading = false,
}) => {
  const stripe = useStripe();
  const elements = useElements();

  const [cardError, setCardError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [cardComplete, setCardComplete] = useState(false);

  const handleCardChange = (event: StripeCardElementChangeEvent) => {
    setCardError(event.error?.message ?? null);
    setCardComplete(event.complete);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!stripe || !elements) {
      return;
    }

    const cardElement = elements.getElement(CardElement);
    if (!cardElement) {
      setCardError('Card element not found. Please refresh and try again.');
      return;
    }

    setProcessing(true);
    setCardError(null);

    try {
      const { error, paymentIntent } = await stripe.confirmCardPayment(clientSecret, {
        payment_method: {
          card: cardElement,
        },
      });

      if (error) {
        setCardError(error.message ?? 'Payment failed. Please try again.');
      } else if (paymentIntent && paymentIntent.status === 'succeeded') {
        onPaymentComplete(paymentIntent.id);
      } else if (paymentIntent && paymentIntent.status === 'requires_capture') {
        // Manual capture flow for hotel pre-auth
        onPaymentComplete(paymentIntent.id);
      } else {
        setCardError('Unexpected payment status. Please contact support.');
      }
    } catch {
      setCardError('An unexpected error occurred. Please try again.');
    } finally {
      setProcessing(false);
    }
  };

  const disabled = !stripe || !elements || processing || isLoading || !cardComplete;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <h2 className="font-display text-xl font-semibold text-neutral-900">Payment</h2>

      <StripeCardElement onChange={handleCardChange} error={cardError} />

      <button
        type="submit"
        disabled={disabled}
        className="w-full rounded-lg bg-accent-500 py-3 text-sm font-semibold text-white hover:bg-accent-600 focus:outline-hidden focus:ring-2 focus:ring-accent-400 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
      >
        {processing || isLoading ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Processing Payment...
          </span>
        ) : (
          `Pay $${amount.toFixed(2)}`
        )}
      </button>

      <p className="text-center text-xs text-neutral-400">
        By completing this payment you agree to our terms of service and cancellation policy.
      </p>
    </form>
  );
};

export default PaymentForm;
