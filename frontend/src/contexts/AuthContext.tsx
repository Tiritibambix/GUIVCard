import React, { createContext, useContext, useState, useCallback } from 'react';
import { api } from '../services/api';

interface AuthContextType {
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);

  const login = useCallback(async (username: string, password: string) => {
    try {
      // Configure api instance with basic auth
      api.defaults.auth = {
        username,
        password
      };

      // Test authentication with health check endpoint
      await api.get('/api/health');
      
      // Store credentials in localStorage
      localStorage.setItem('auth', btoa(`${username}:${password}`));
      setIsAuthenticated(true);
    } catch (error) {
      localStorage.removeItem('auth');
      setIsAuthenticated(false);
      throw new Error('Authentication failed');
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('auth');
    delete api.defaults.auth;
    setIsAuthenticated(false);
  }, []);

  // Check for stored credentials on mount
  React.useEffect(() => {
    const storedAuth = localStorage.getItem('auth');
    if (storedAuth) {
      const [username, password] = atob(storedAuth).split(':');
      api.defaults.auth = { username, password };
      setIsAuthenticated(true);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;