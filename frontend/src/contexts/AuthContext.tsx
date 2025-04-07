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

      // Test authentication with protected health check endpoint
      const response = await api.get('/api/health');
      
      if (response.data.status === 'healthy') {
        // Store auth info with expiration (2 hours)
        const expiresAt = new Date().getTime() + (2 * 60 * 60 * 1000);
        const authInfo = {
          credentials: btoa(`${username}:${password}`),
          expiresAt
        };
        sessionStorage.setItem('auth', JSON.stringify(authInfo));
        setIsAuthenticated(true);
      } else {
        throw new Error('Service unhealthy');
      }
    } catch (error) {
      localStorage.removeItem('auth');
      setIsAuthenticated(false);
      throw new Error('Authentication failed');
    }
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem('auth');
    delete api.defaults.auth;
    setIsAuthenticated(false);
    // Force reload to clear any cached data
    window.location.href = '/login';
  }, []);

  // Check for stored credentials on mount
  React.useEffect(() => {
    const storedAuth = sessionStorage.getItem('auth');
    if (storedAuth) {
      try {
        const authInfo = JSON.parse(storedAuth);
        const now = new Date().getTime();
        
        if (now < authInfo.expiresAt) {
          const [username, password] = atob(authInfo.credentials).split(':');
          api.defaults.auth = { username, password };
          setIsAuthenticated(true);
        } else {
          sessionStorage.removeItem('auth');
          setIsAuthenticated(false);
        }
      } catch (error) {
        sessionStorage.removeItem('auth');
        setIsAuthenticated(false);
      }
    }
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;