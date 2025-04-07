import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8191';

// Create an axios instance with default config
export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login if authentication fails
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);