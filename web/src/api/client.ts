import axios from 'axios';

// Use Vite dev server proxy in development; in production rely on same-origin
// nginx proxy (or explicit VITE_API_URL if provided).
const API_BASE_URL = import.meta.env.DEV ? '/' : (import.meta.env.VITE_API_URL || '');

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('[API Error]', error.response?.status, error.message);
    return Promise.reject(error);
  }
);

export default apiClient;
