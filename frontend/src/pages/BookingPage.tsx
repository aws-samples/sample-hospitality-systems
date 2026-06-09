import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Elements } from '@stripe/react-stripe-js';
import { loadStripe } from '@stripe/stripe-js';
import { useAuth } from '../context/AuthContext';
import { useCart } from '../context/CartContext';
import * as bookingService from '../services/bookingService';
import * as paymentService from '../services/paymentService';
import GuestInfoForm, { type GuestInfoData } from '../components/booking/GuestInfoForm';
import BookingSummary from '../components/booking/BookingSummary';
import PromoCodeInput from '../components/booking/PromoCodeInput';
import PaymentForm from '../components/payment/PaymentForm';
import LoadingSpinner from '../components/common/LoadingSpinner';
import PublicLayout from '../components/layout/PublicLayout';
import config from '../config/aws-config';

const stripePromise = loadStripe(config.stripePublishableKey ?? '');

type BookingStep = 1 | 2 | 3;

const STEP_LABELS = ['Guest Info', 'Review', 'Payment'];

const BookingPage: React.FC = () => {
  const { cartId } = useParams<{ cartId: string }>();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const { cart, applyPromo, clearCart } = useCart();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<BookingStep>(() => {
    const saved = sessionStorage.getItem(`booking_step_${cartId}`);
    return saved ? (Number(saved) as BookingStep) : 1;
  });
  const [guestInfo, setGuestInfo] = useState<GuestInfoData | null>(() => {
    const saved = sessionStorage.getItem(`booking_guest_${cartId}`);
    return saved ? JSON.parse(saved) : null;
  });
  const [promoError, setPromoError] = useState<string | null>(null);
  const [promoLoading, setPromoLoading] = useState(false);

  // Create payment intent for step 3
  const {
    data: paymentIntent,
    mutate: createPaymentIntent,
    isPending: paymentIntentLoading,
  } = useMutation({
    mutationFn: () =>
      paymentService.createPaymentIntent({
        amount: cart?.pricing.total ?? 0,
        currency: cart?.pricing.currency ?? 'usd',
        reservationId: '', // Will be set after booking
        guestId: user?.guestId ?? '',
        description: `Booking at ${cart?.property.name}`,
        captureMethod: 'manual',
      }),
  });

  // Complete booking mutation
  const completeMutation = useMutation({
    mutationFn: (paymentIntentId: string) => {
      if (!cartId || !guestInfo || !user) throw new Error('Missing booking data');
      return bookingService.completeBooking(cartId, {
        guestId: user.guestId,
        paymentMethodId: paymentIntentId,
        specialRequests: guestInfo.specialRequests,
        guests: [
          {
            firstName: guestInfo.firstName,
            lastName: guestInfo.lastName,
            email: guestInfo.email,
            phone: guestInfo.phone,
          },
        ],
      });
    },
    onSuccess: (confirmation) => {
      queryClient.invalidateQueries({ queryKey: ['reservations'] });
      clearCart();
      sessionStorage.removeItem(`booking_guest_${cartId}`);
      sessionStorage.removeItem(`booking_step_${cartId}`);
      navigate(`/confirmation/${confirmation.confirmationNumber}`);
    },
  });

  // Redirect if no cart
  useEffect(() => {
    if (!cart && !cartId) {
      navigate('/');
    }
  }, [cart, cartId, navigate]);

  // Auto-advance to payment if returning from sign-in with saved guest info
  useEffect(() => {
    if (isAuthenticated && cart && guestInfo && step === 2) {
      const returnedFromSignIn = sessionStorage.getItem(`booking_step_${cartId}`);
      if (returnedFromSignIn === '2') {
        sessionStorage.removeItem(`booking_step_${cartId}`);
        sessionStorage.removeItem(`booking_guest_${cartId}`);
        setStep(3);
        createPaymentIntent();
      }
    }
  }, [isAuthenticated, cart, guestInfo, step, cartId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!cart) {
    return (
      <PublicLayout>
        <div className="flex min-h-[60vh] items-center justify-center">
          <LoadingSpinner size="lg" message="Loading your booking..." />
        </div>
      </PublicLayout>
    );
  }

  const handleGuestInfoSubmit = (data: GuestInfoData) => {
    setGuestInfo(data);
    setStep(2);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePromoApply = async (code: string) => {
    if (!cartId) return;
    setPromoLoading(true);
    setPromoError(null);
    try {
      await applyPromo(cartId, code);
    } catch {
      setPromoError('Invalid promo code. Please try again.');
    } finally {
      setPromoLoading(false);
    }
  };

  const handleProceedToPayment = () => {
    if (!isAuthenticated) {
      // Save guest info and step so we can restore after sign-in
      if (guestInfo) {
        sessionStorage.setItem(`booking_guest_${cartId}`, JSON.stringify(guestInfo));
        sessionStorage.setItem(`booking_step_${cartId}`, '2');
      }
      navigate(`/signin?returnUrl=/booking/${cartId}`);
      return;
    }
    setStep(3);
    createPaymentIntent();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePaymentComplete = (paymentIntentId: string) => {
    completeMutation.mutate(paymentIntentId);
  };

  return (
    <PublicLayout>
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Step indicator */}
        <nav className="mb-10">
          <ol className="flex items-center justify-center gap-4">
            {STEP_LABELS.map((label, idx) => {
              const stepNum = (idx + 1) as BookingStep;
              const isActive = step === stepNum;
              const isComplete = step > stepNum;

              return (
                <li key={label} className="flex items-center gap-2">
                  {idx > 0 && (
                    <div
                      className={`h-px w-8 sm:w-16 ${
                        isComplete ? 'bg-primary-600' : 'bg-neutral-300'
                      }`}
                    />
                  )}
                  <div className="flex items-center gap-2">
                    <span
                      className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${
                        isActive
                          ? 'bg-primary-600 text-white'
                          : isComplete
                          ? 'bg-primary-600 text-white'
                          : 'bg-neutral-200 text-neutral-500'
                      }`}
                    >
                      {isComplete ? (
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                        </svg>
                      ) : (
                        stepNum
                      )}
                    </span>
                    <span
                      className={`hidden text-sm font-medium sm:inline ${
                        isActive ? 'text-primary-600' : isComplete ? 'text-primary-600' : 'text-neutral-400'
                      }`}
                    >
                      {label}
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        </nav>

        <div className="grid gap-8 lg:grid-cols-3">
          {/* Main content */}
          <div className="lg:col-span-2">
            {/* Step 1: Guest Info */}
            {step === 1 && (
              <GuestInfoForm onSubmit={handleGuestInfoSubmit} />
            )}

            {/* Step 2: Review */}
            {step === 2 && guestInfo && (
              <div className="space-y-6">
                <h2 className="font-display text-xl font-semibold text-neutral-900">
                  Review Your Booking
                </h2>

                {/* Guest info summary */}
                <div className="rounded-xl border border-neutral-200 bg-white p-5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-neutral-800">Guest Information</h3>
                    <button
                      type="button"
                      onClick={() => setStep(1)}
                      className="text-sm font-medium text-primary-600 hover:text-primary-700"
                    >
                      Edit
                    </button>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-neutral-500">Name</span>
                      <p className="font-medium text-neutral-800">
                        {guestInfo.firstName} {guestInfo.lastName}
                      </p>
                    </div>
                    <div>
                      <span className="text-neutral-500">Email</span>
                      <p className="font-medium text-neutral-800">{guestInfo.email}</p>
                    </div>
                    {guestInfo.phone && (
                      <div>
                        <span className="text-neutral-500">Phone</span>
                        <p className="font-medium text-neutral-800">{guestInfo.phone}</p>
                      </div>
                    )}
                    {guestInfo.specialRequests && (
                      <div className="col-span-2">
                        <span className="text-neutral-500">Special Requests</span>
                        <p className="font-medium text-neutral-800">{guestInfo.specialRequests}</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Promo code */}
                <div className="rounded-xl border border-neutral-200 bg-white p-5">
                  <PromoCodeInput
                    onApply={handlePromoApply}
                    isLoading={promoLoading}
                    discount={cart.discountAmount || null}
                    error={promoError}
                  />
                </div>

                {/* Sign-in prompt for unauthenticated users */}
                {!isAuthenticated && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
                    <p className="text-sm font-medium text-amber-800">
                      Please sign in to complete your booking. Your cart will be saved.
                    </p>
                  </div>
                )}

                {/* Proceed to payment */}
                <button
                  type="button"
                  onClick={handleProceedToPayment}
                  className="w-full rounded-lg bg-primary-600 py-3 text-sm font-semibold text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-600/40 transition-colors"
                >
                  {isAuthenticated ? 'Proceed to Payment' : 'Sign In to Continue'}
                </button>
              </div>
            )}

            {/* Step 3: Payment */}
            {step === 3 && (
              <div>
                {paymentIntentLoading ? (
                  <div className="flex justify-center py-12">
                    <LoadingSpinner message="Preparing payment..." />
                  </div>
                ) : paymentIntent?.clientSecret ? (
                  <Elements
                    stripe={stripePromise}
                    options={{ clientSecret: paymentIntent.clientSecret }}
                  >
                    <PaymentForm
                      amount={cart.pricing.total}
                      clientSecret={paymentIntent.clientSecret}
                      onPaymentComplete={handlePaymentComplete}
                      isLoading={completeMutation.isPending}
                    />
                  </Elements>
                ) : (
                  <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
                    <p className="text-red-600">
                      Unable to initialize payment. Please try again.
                    </p>
                    <button
                      type="button"
                      onClick={() => createPaymentIntent()}
                      className="mt-4 rounded-lg bg-primary-600 px-6 py-2 text-sm font-semibold text-white hover:bg-primary-700"
                    >
                      Retry
                    </button>
                  </div>
                )}

                {completeMutation.isError && (
                  <div className="mt-4 rounded-lg bg-red-50 p-4 text-sm text-red-600">
                    Booking failed. Please try again or contact support.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Sidebar: Booking Summary */}
          <div className="lg:col-span-1">
            <div className="sticky top-20">
              <BookingSummary cart={cart} />
            </div>
          </div>
        </div>
      </div>
    </PublicLayout>
  );
};

export default BookingPage;
