import api from './api';

export interface SearchParams {
  destination: string;
  checkIn: string;
  checkOut: string;
  adults: number;
  children?: number;
  rooms?: number;
  minPrice?: number;
  maxPrice?: number;
  amenities?: string[];
  starRating?: number;
}

export interface SearchResult {
  propertyId: string;
  propertyName: string;
  propertyDescription: string;
  city: string;
  state: string;
  country: string;
  starRating: number;
  heroImageUrl: string | null;
  propertyAmenities: string[];
  isFeatured: boolean;
  cheapestOption?: {
    roomTypeId: string;
    roomTypeName: string;
    ratePlanId: string;
    ratePlanName: string;
    cancellationPolicy: string;
    pricePerNight: string;
    totalBeforeTax: string;
    totalAfterTax: string;
    numNights: number;
  };
}

export interface RateParams {
  propertyId: string;
  roomTypeId: string;
  checkIn: string;
  checkOut: string;
  adults: number;
  children?: number;
}

export interface RateResult {
  ratePlanId: string;
  name: string;
  code: string;
  description: string;
  cancellationPolicy: string;
  nightlyRates: {
    date: string;
    amount: number;
    currency: string;
  }[];
  totalAmount: number;
  taxes: number;
  fees: number;
  currency: string;
}

export interface CreateCartParams {
  propertyId: string;
  roomTypeId: string;
  ratePlanId: string;
  checkIn: string;
  checkOut: string;
  adults: number;
  children?: number;
}

export interface UpdateCartParams {
  roomTypeId?: string;
  ratePlanId?: string;
  checkIn?: string;
  checkOut?: string;
  adults?: number;
  children?: number;
}

export interface CompleteBookingData {
  guestId: string;
  paymentMethodId: string;
  specialRequests?: string;
  loyaltyNumber?: string;
  guests: {
    firstName: string;
    lastName: string;
    email: string;
    phone?: string;
  }[];
}

export interface BookingConfirmation {
  confirmationNumber: string;
  reservationId: string;
  status: string;
  property: {
    propertyId: string;
    name: string;
  };
  dates: {
    checkIn: string;
    checkOut: string;
  };
  totalAmount: number;
  currency: string;
}

export async function searchProperties(params: SearchParams): Promise<SearchResult[]> {
  const response = await api.post('/booking/search', params);
  return response.data;
}

export async function getRates(params: RateParams): Promise<RateResult[]> {
  const response = await api.get('/booking/rates', { params });
  return response.data;
}

export async function createCart(params: CreateCartParams): Promise<unknown> {
  const response = await api.post('/booking/cart', params);
  return response.data;
}

export async function updateCart(cartId: string, params: UpdateCartParams): Promise<unknown> {
  const response = await api.put(`/booking/cart/${cartId}`, params);
  return response.data;
}

export async function applyPromo(cartId: string, code: string): Promise<unknown> {
  const response = await api.post(`/booking/cart/${cartId}/promo`, { code });
  return response.data;
}

export async function completeBooking(
  cartId: string,
  data: CompleteBookingData
): Promise<BookingConfirmation> {
  const response = await api.post(`/booking/cart/${cartId}/book`, data);
  return response.data;
}
