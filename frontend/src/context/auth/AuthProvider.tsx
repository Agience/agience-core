import React, { useState, ReactNode, useEffect, useCallback } from 'react';
import { get, del } from '../../api/api';
import { getRuntimeConfig } from '../../config/runtime';
import { User } from './auth.types';
import { AuthContext } from './AuthContext';

const { backendUri: BACKEND_URI, clientId: CLIENT_ID } = getRuntimeConfig();

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const localToken = localStorage.getItem('access_token');
    console.log('[AuthProvider] mount — token in localStorage:', !!localToken);
    if (!localToken) {
      setLoading(false);
      return;
    }
    setToken(localToken);
  }, []);

  useEffect(() => {
    if (!token) return;

    const controller = new AbortController();
    setLoading(true);
    console.log('[AuthProvider] token effect — fetching /auth/userinfo');
    get<User>('/auth/userinfo', { signal: controller.signal })
      .then((res) => {
        console.log('[AuthProvider] /auth/userinfo OK — user:', res?.email ?? res?.name ?? 'unknown');
        setUser(res);
        setIsAuthenticated(true);
      })
      .catch((err) => {
        if (controller.signal.aborted || err?.code === 'ERR_CANCELED') {
          console.log('[AuthProvider] /auth/userinfo aborted (cleanup)');
          return;
        }
        console.warn('[AuthProvider] /auth/userinfo FAILED:', err);
        localStorage.removeItem('access_token');
        setToken(null);
        setUser(null);
        setIsAuthenticated(false);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          console.log('[AuthProvider] loading → false');
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [token]);

  const setAuthData = (token: string | null) => {
    if (!token) {
      localStorage.removeItem('access_token');
      setToken(null);
      setUser(null);
      setIsAuthenticated(false);
      return;
    }

    console.log('[AuthProvider] setAuthData — storing token, triggering validation');
    localStorage.setItem('access_token', token);
    setLoading(true);  // must be synchronous so LoginProtected shows spinner
    setToken(token);    // triggers validation effect
    setUser(null);      // clear stale user
  };

  const login = async (provider: string = 'google', setupOperatorToken?: string) => {
    const state = crypto.randomUUID();
    const codeVerifier = Array.from(crypto.getRandomValues(new Uint8Array(32)))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');

    const encoder = new TextEncoder();
    const data = encoder.encode(codeVerifier);
    const digest = await crypto.subtle.digest('SHA-256', data);
    const base64Url = btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

    localStorage.setItem('pkce_state', state);
    localStorage.setItem('pkce_verifier', codeVerifier);

    const params = new URLSearchParams({
      response_type: 'code',
      client_id: CLIENT_ID,
      redirect_uri: `${window.location.origin}/auth/callback`,
      scope: 'openid email profile',
      state,
      code_challenge: base64Url,
      code_challenge_method: 'S256',
      provider,
    });
    if (setupOperatorToken) {
      params.set('setup_operator_token', setupOperatorToken);
    }

    window.location.href = `${BACKEND_URI}/auth/authorize?${params.toString()}`;
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    setToken(null);
    setUser(null);
    setIsAuthenticated(false);
  };

  // Force a fresh /userinfo fetch (e.g. after linking a provider)
  const refreshUser = useCallback(() => {
    const t = localStorage.getItem('access_token');
    if (!t) return;
    get<User>('/auth/userinfo')
      .then((res) => setUser(res))
      .catch(() => {/* silent */});
  }, []);

  // Start an OIDC provider link flow for the currently logged-in user.
  // Stores a 'linking_provider' marker in sessionStorage so AuthCallback
  // knows to call POST /auth/me/link-provider instead of /auth/token.
  const startLinkProvider = async (provider: string) => {
    const state = crypto.randomUUID();
    const codeVerifier = Array.from(crypto.getRandomValues(new Uint8Array(32)))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
    const encoder = new TextEncoder();
    const digest = await crypto.subtle.digest('SHA-256', encoder.encode(codeVerifier));
    const base64Url = btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

    localStorage.setItem('pkce_state', state);
    localStorage.setItem('pkce_verifier', codeVerifier);
    // Signal AuthCallback to perform a link (not login) after the dance
    sessionStorage.setItem('linking_provider', provider);

    const params = new URLSearchParams({
      response_type: 'code',
      client_id: CLIENT_ID,
      redirect_uri: `${window.location.origin}/auth/callback`,
      scope: 'openid email profile',
      state,
      code_challenge: base64Url,
      code_challenge_method: 'S256',
      provider,
    });
    window.location.href = `${BACKEND_URI}/auth/authorize?${params.toString()}`;
  };

  // Unlink the given provider from the current user's account.
  const unlinkProvider = async (provider: string) => {
    await del(`/auth/me/link-provider/${encodeURIComponent(provider)}`);
    refreshUser();
  };

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, user, login, startLinkProvider, unlinkProvider, logout, loading, setAuthData, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
};
