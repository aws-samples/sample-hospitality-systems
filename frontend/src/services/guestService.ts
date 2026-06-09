import api from './api';
import axios from 'axios';
import config from '@/config/aws-config';

export interface CreateGuestData {
  firstName: string;
  lastName: string;
  email: string;
  cognitoSub: string;
  phone?: string;
}

export interface Guest {
  guestId: string;
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  cognitoSub: string;
  loyaltyNumber: string;
  loyaltyTier: string;
  preferences: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface UpdateGuestData {
  firstName?: string;
  lastName?: string;
  phone?: string;
  preferences?: Record<string, unknown>;
}

/**
 * Create a guest profile. Accepts an optional token parameter
 * for use during sign-in before the interceptor token getter is set.
 */
export async function createGuest(
  data: CreateGuestData,
  token?: string
): Promise<Guest> {
  if (token) {
    // Direct call with explicit token (used during sign-in flow)
    const response = await axios.post(`${config.apiUrl}/guests`, data, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });
    // Unwrap envelope if present
    if (response.data && typeof response.data === 'object' && 'data' in response.data) {
      return response.data.data;
    }
    return response.data;
  }

  const response = await api.post('/guests', data);
  return response.data;
}

export async function getGuest(guestId: string): Promise<Guest> {
  const response = await api.get(`/guests/${guestId}`);
  return response.data;
}

export async function updateGuest(
  guestId: string,
  data: UpdateGuestData
): Promise<Guest> {
  const response = await api.put(`/guests/${guestId}`, data);
  return response.data;
}
