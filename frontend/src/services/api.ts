import axios, { type AxiosInstance, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios';
import config from '@/config/aws-config';

// Token getter will be set by the auth context initialization
let tokenGetter: (() => Promise<string | null>) | null = null;

export function setTokenGetter(getter: () => Promise<string | null>): void {
  tokenGetter = getter;
}

const api: AxiosInstance = axios.create({
  baseURL: config.apiUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: attach auth token and correlation ID
api.interceptors.request.use(
  async (requestConfig: InternalAxiosRequestConfig) => {
    // Add correlation ID
    requestConfig.headers.set('X-Correlation-Id', crypto.randomUUID());

    // Add auth token if available
    if (tokenGetter) {
      const token = await tokenGetter();
      if (token) {
        requestConfig.headers.set('Authorization', `Bearer ${token}`);
      }
    }

    return requestConfig;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: unwrap API envelope, handle 401
api.interceptors.response.use(
  (response: AxiosResponse) => {
    // Unwrap the standard response envelope: { success, data, metadata }
    if (response.data && typeof response.data === 'object' && 'data' in response.data) {
      response.data = response.data.data;
    }
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      // Clear auth-related state but preserve booking cart
      for (const key of Object.keys(sessionStorage)) {
        if (key.startsWith('guestId_')) {
          sessionStorage.removeItem(key);
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
