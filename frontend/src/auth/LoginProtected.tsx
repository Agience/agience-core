import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const LoginProtected: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  const hasGrantKeys = (() => {
    // If a grant key is present in the URL, allow entry immediately
    // (GrantKeyCapture will persist it right after mount).
    try {
      const params = new URLSearchParams(location.search);
      if (params.get('grant_key')) return true;
    } catch {
      // ignore
    }

    // Check grant_keys storage key.
    const raw = sessionStorage.getItem('grant_keys') ?? localStorage.getItem('grant_keys');
    if (!raw) return false;
    try {
      const val = JSON.parse(raw);
      return Array.isArray(val) && val.length > 0;
    } catch {
      return false;
    }
  })();

  if (loading) {
    console.log('[LoginProtected] loading — showing spinner');
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-gray-900"></div>
      </div>
    );
  }

  if (!isAuthenticated && !hasGrantKeys) {
    console.log('[LoginProtected] not authenticated — redirecting to /login');
    // Redirect to login page with the intended destination
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  console.log('[LoginProtected] authenticated — rendering app');
  return <>{children}</>;
};

export default LoginProtected; 