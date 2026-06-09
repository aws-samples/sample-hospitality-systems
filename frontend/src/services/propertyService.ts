import api from './api';

export interface PropertySearchParams {
  city?: string;
  country?: string;
  brand?: string;
  amenities?: string[];
  minStarRating?: number;
  page?: number;
  limit?: number;
}

export interface Property {
  propertyId: string;
  name: string;
  brand: string;
  address: {
    street: string;
    city: string;
    state: string;
    country: string;
    postalCode: string;
  };
  starRating: number;
  description: string;
  amenities: string[];
  images: string[];
  coordinates: {
    latitude: number;
    longitude: number;
  };
}

export interface RoomType {
  roomTypeId: string;
  propertyId: string;
  name: string;
  description: string;
  category: string;
  maxOccupancy: number;
  bedConfiguration: string;
  amenities: string[];
  images: string[];
  baseRate: number;
  squareFootage: number;
}

export async function getProperties(params?: PropertySearchParams): Promise<Property[]> {
  const response = await api.get('/properties', { params });
  return response.data;
}

export async function getProperty(propertyId: string): Promise<Property> {
  const response = await api.get(`/properties/${propertyId}`);
  return response.data;
}

export async function getRoomTypes(propertyId: string): Promise<RoomType[]> {
  const response = await api.get(`/properties/${propertyId}/room-types`);
  return response.data;
}

export async function getRoomType(propertyId: string, roomTypeId: string): Promise<RoomType> {
  const response = await api.get(`/properties/${propertyId}/room-types/${roomTypeId}`);
  return response.data;
}
