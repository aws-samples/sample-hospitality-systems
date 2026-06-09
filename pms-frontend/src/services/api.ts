/**
 * PMS API client with Cognito JWT authentication.
 */

import axios, { AxiosInstance } from 'axios';

const PMS_API_URL = import.meta.env.VITE_PMS_API_URL || '';

export const pmsApi: AxiosInstance = axios.create({
  baseURL: PMS_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: attach JWT token
pmsApi.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('pms_id_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Add correlation ID
  config.headers['X-Correlation-Id'] = crypto.randomUUID();

  return config;
});

// Response interceptor: unwrap envelope
pmsApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired — redirect to sign in
      sessionStorage.removeItem('pms_id_token');
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);
