import axios, { AxiosResponse, AxiosError } from 'axios';

// Access runtime environment configuration
declare global {
  interface Window {
    ENV: {
      API_URL: string;
    };
  }
}

const API_URL = window.ENV?.API_URL || 'http://localhost:8191';

// Create an axios instance with default config
export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add response interceptor for error handling
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Redirect to login if authentication fails
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);