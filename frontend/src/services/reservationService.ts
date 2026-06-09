import api from './api';

export interface ReservationSearchParams {
  guestId?: string;
  status?: string;
  checkInFrom?: string;
  checkInTo?: string;
  page?: number;
  limit?: number;
}

export interface Reservation {
  reservationId: string;
  confirmationNumber: string;
  status: string;
  guestId: string;
  propertyId: string;
  propertyName: string;
  roomTypeId: string;
  roomTypeName: string;
  ratePlanCode: string;
  checkInDate: string;
  checkOutDate: string;
  adults: number;
  children: number;
  totalAmount: number;
  currency: string;
  specialRequests: string;
  createdAt: string;
  updatedAt: string;
}

export interface CancelReservationResponse {
  reservationId: string;
  status: string;
  cancellationFee: number;
  refundAmount: number;
}

export async function getReservations(
  params?: ReservationSearchParams
): Promise<Reservation[]> {
  const response = await api.get('/reservations', { params });
  return response.data;
}

export async function getReservation(reservationId: string): Promise<Reservation> {
  const response = await api.get(`/reservations/${reservationId}`);
  return response.data;
}

export async function cancelReservation(
  reservationId: string,
  reason?: string
): Promise<CancelReservationResponse> {
  const response = await api.delete(`/reservations/${reservationId}`, {
    data: { reason },
  });
  return response.data;
}
