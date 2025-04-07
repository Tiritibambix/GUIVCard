import axios, { AxiosResponse, AxiosError } from 'axios';

// Access runtime environment configuration
declare global {
  interface Window {
    ENV: {
      VITE_API_URL: string;
    };
  }
}

const API_URL = window.ENV?.VITE_API_URL || import.meta.env.VITE_API_URL || 'http://localhost:8195';

// Create an axios instance with default config
export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
  // Ensure credentials are sent with every request
  auth: {
    username: '',  // Will be set by AuthContext
    password: ''   // Will be set by AuthContext
  }
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