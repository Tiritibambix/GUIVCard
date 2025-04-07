import React, { createContext, useContext, useState, useCallback } from 'react';
import axios from 'axios';

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
      // Configure axios with basic auth
      axios.defaults.auth = {
        username,
        password
      };

      // Test authentication with health check endpoint
      await axios.get(`${process.env.REACT_APP_API_URL}/api/health`);
      setIsAuthenticated(true);
    } catch (error) {
      setIsAuthenticated(false);
      throw new Error('Authentication failed');
    }
  }, []);

  const logout = useCallback(() => {
    delete axios.defaults.auth;
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;