import api from './api';

export interface CreatePaymentIntentData {
  amount: number;
  currency: string;
  reservationId: string;
  guestId: string;
  description?: string;
  captureMethod?: 'manual' | 'automatic';
}

export interface PaymentIntent {
  paymentIntentId: string;
  stripePaymentIntentId: string;
  clientSecret: string;
  amount: number;
  currency: string;
  status: string;
  reservationId: string;
  guestId: string;
  createdAt: string;
}

export interface ConfirmPaymentData {
  paymentIntentId: string;
  paymentMethodId: string;
}

export interface PaymentConfirmation {
  paymentIntentId: string;
  status: string;
  amount: number;
  currency: string;
  confirmedAt: string;
}

export interface Payment {
  paymentId: string;
  paymentIntentId: string;
  stripePaymentIntentId: string;
  amount: number;
  currency: string;
  status: string;
  reservationId: string;
  guestId: string;
  paymentMethodId: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreatePaymentMethodData {
  stripePaymentMethodId: string;
  guestId: string;
  isDefault?: boolean;
}

export interface PaymentMethod {
  paymentMethodId: string;
  stripePaymentMethodId: string;
  guestId: string;
  brand: string;
  last4: string;
  expiryMonth: number;
  expiryYear: number;
  isDefault: boolean;
  createdAt: string;
}

export async function createPaymentIntent(
  data: CreatePaymentIntentData
): Promise<PaymentIntent> {
  const response = await api.post('/payments/intents', data);
  return response.data;
}

export async function confirmPayment(
  data: ConfirmPaymentData
): Promise<PaymentConfirmation> {
  const response = await api.post('/payments/confirm', data);
  return response.data;
}

export async function getPayment(paymentId: string): Promise<Payment> {
  const response = await api.get(`/payments/${paymentId}`);
  return response.data;
}

export async function createPaymentMethod(
  data: CreatePaymentMethodData
): Promise<PaymentMethod> {
  const response = await api.post('/payment-methods', data);
  return response.data;
}

export async function getPaymentMethods(): Promise<PaymentMethod[]> {
  const response = await api.get('/payment-methods');
  return response.data;
}
