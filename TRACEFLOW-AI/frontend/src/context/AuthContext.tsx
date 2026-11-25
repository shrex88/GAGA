import React, { createContext, useContext, useEffect, useState } from 'react';
import { api } from '../services/api';
import { User } from '../types';

interface BackendHealth {
  status: string;
  auth_mode?: string;
  database?: { connected: boolean; error?: string | null };
  graph?: { backend_mode: string; neo4j_connected: boolean };
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  health: BackendHealth | null;
  connectionError: string;
  switchRole: (roleName: string) => Promise<void>;
  hasPermission: (perm: string) => boolean;
  retryConnection: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [connectionError, setConnectionError] = useState<string>('');

  const loadSessionAndHealth = async () => {
    setLoading(true);
    setConnectionError('');
    try {
      const [healthRes, meRes] = await Promise.all([
        api.get('/health'),
        api.get('/auth/me'),
      ]);
      setHealth(healthRes.data);
      setUser(meRes.data);
    } catch (err: any) {
      const status = err.response?.status;
      if (!err.response || err.code === 'ERR_NETWORK' || status === 502 || status === 504) {
        setConnectionError('Cannot reach TRACEFLOW AI backend on port 8000. Ensure the FastAPI server is running.');
      } else {
        setConnectionError(err.response?.data?.detail || `Backend error (HTTP ${status || 'unknown'}).`);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSessionAndHealth();
  }, []);

  const switchRole = async (roleName: string) => {
    localStorage.setItem('tf_demo_role', roleName);
    await loadSessionAndHealth();
  };

  const hasPermission = (perm: string) => {
    return !!user?.permissions?.includes(perm);
  };

  if (connectionError && !user) {
    return (
      <div className="min-h-screen bg-[#050914] flex items-center justify-center p-6">
        <div className="tf-card rounded-xl p-6 max-w-md text-center space-y-3">
          <div className="text-sm font-semibold text-rose-400">Backend Connection Unavailable</div>
          <p className="text-xs text-slate-300">{connectionError}</p>
          <button
            onClick={loadSessionAndHealth}
            className="px-4 py-2 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-lg"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        health,
        connectionError,
        switchRole,
        hasPermission,
        retryConnection: loadSessionAndHealth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};
