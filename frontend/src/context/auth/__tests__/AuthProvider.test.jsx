// src/context/auth/__tests__/AuthProvider.test.jsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { AuthProvider } from '../AuthProvider';
import { useAuth } from '../../../hooks/useAuth';

// Mock the API module
vi.mock('../../../api/api', () => ({
  get: vi.fn(),
}));

import { get } from '../../../api/api';

// Test component that uses AuthContext
function TestConsumer() {
  const auth = useAuth();
  
  return (
    <div>
      <div data-testid="loading">{auth.loading ? 'loading' : 'ready'}</div>
      <div data-testid="authenticated">{auth.isAuthenticated ? 'yes' : 'no'}</div>
      <div data-testid="user">{auth.user ? auth.user.email : 'none'}</div>
      <button onClick={auth.login}>Login</button>
      <button onClick={auth.logout}>Logout</button>
      <button onClick={() => auth.setAuthData('test-token')}>Set Token</button>
      <button onClick={() => auth.setAuthData(null)}>Clear Token</button>
    </div>
  );
}

describe('AuthProvider', () => {
  const mockUser = {
    id: 'user-1',
    email: 'test@example.com',
    name: 'Test User',
    picture: 'https://example.com/pic.jpg'
  };

  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
    vi.clearAllMocks();
    
    // Mock window.location
    delete window.location;
    window.location = { href: '', origin: 'http://localhost:3000' };
    
    // Mock crypto.subtle for PKCE
    const cryptoMock = {
      randomUUID: vi.fn(() => 'mock-uuid'),
      getRandomValues: vi.fn((arr) => {
        for (let i = 0; i < arr.length; i++) {
          arr[i] = i;
        }
        return arr;
      }),
      subtle: {
        digest: vi.fn(() => Promise.resolve(new Uint8Array(32).buffer)),
      },
    };
    vi.stubGlobal('crypto', cryptoMock);
  });

  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  describe('Initial State', () => {
    it('starts unauthenticated when no token in localStorage', async () => {
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
      expect(screen.getByTestId('user')).toHaveTextContent('none');
    });

    it('attempts to validate token when found in localStorage', async () => {
      localStorage.setItem('access_token', 'existing-token');
      get.mockResolvedValueOnce(mockUser);
      
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      expect(get).toHaveBeenCalledWith(
        '/auth/userinfo',
        expect.objectContaining({ signal: expect.any(Object) }),
      );
      expect(screen.getByTestId('authenticated')).toHaveTextContent('yes');
      expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
    });

    it('clears invalid token from localStorage', async () => {
      localStorage.setItem('access_token', 'invalid-token');
      get.mockRejectedValueOnce(new Error('Unauthorized'));
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });

      expect(warnSpy).toHaveBeenCalledWith('[AuthProvider] /auth/userinfo FAILED:', expect.any(Error));
      warnSpy.mockRestore();
      
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
    });
  });

  describe('login()', () => {
    it('initiates PKCE OAuth flow', async () => {
      const user = userEvent.setup();
      
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      await user.click(screen.getByText('Login'));
      
      // Verify PKCE state stored in localStorage
      expect(localStorage.getItem('pkce_state')).toBe('mock-uuid');
      expect(localStorage.getItem('pkce_verifier')).toBeTruthy();
      
      // Verify redirect URL contains OAuth params
      expect(window.location.href).toContain('/auth/authorize');
      expect(window.location.href).toContain('response_type=code');
      expect(window.location.href).toContain('code_challenge=');
      expect(window.location.href).toContain('code_challenge_method=S256');
    });

    it('includes client_id and redirect_uri in OAuth flow', async () => {
      const user = userEvent.setup();
      
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      await user.click(screen.getByText('Login'));

      const url = new URL(window.location.href);
      expect(url.searchParams.get('client_id')).toBeTruthy();
      expect(url.searchParams.get('redirect_uri')).toBe('http://localhost:3000/auth/callback');
    });
  });

  describe('setAuthData()', () => {
    it('stores token and fetches user info', async () => {
      const user = userEvent.setup();
      get.mockResolvedValueOnce(mockUser);
      
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      await user.click(screen.getByText('Set Token'));
      
      await waitFor(() => {
        expect(screen.getByTestId('authenticated')).toHaveTextContent('yes');
      });
      
      expect(localStorage.getItem('access_token')).toBe('test-token');
      expect(get).toHaveBeenCalledWith(
        '/auth/userinfo',
        expect.objectContaining({ signal: expect.any(Object) }),
      );
      expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
    });

    it('clears auth state when token is null', async () => {
      const user = userEvent.setup();
      get.mockResolvedValueOnce(mockUser);
      
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      // First set a token
      await user.click(screen.getByText('Set Token'));
      await waitFor(() => {
        expect(screen.getByTestId('authenticated')).toHaveTextContent('yes');
      });
      
      // Then clear it
      await user.click(screen.getByText('Clear Token'));
      
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
      expect(screen.getByTestId('user')).toHaveTextContent('none');
    });
  });

  describe('logout()', () => {
    it('clears token and user state', async () => {
      const user = userEvent.setup();
      get.mockResolvedValueOnce(mockUser);
      
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      // First authenticate
      await user.click(screen.getByText('Set Token'));
      await waitFor(() => {
        expect(screen.getByTestId('authenticated')).toHaveTextContent('yes');
      });
      
      // Then logout
      await user.click(screen.getByText('Logout'));
      
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
      expect(screen.getByTestId('user')).toHaveTextContent('none');
    });
  });

  describe('Loading State', () => {
    it('shows loading while verifying token', async () => {
      localStorage.setItem('access_token', 'existing-token');
      let resolveUserInfo;
      const userInfoPromise = new Promise(resolve => {
        resolveUserInfo = resolve;
      });
      get.mockReturnValueOnce(userInfoPromise);
      
      const { container } = render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      // Children render during loading, but the loading indicator shows 'loading'
      expect(screen.getByTestId('loading')).toHaveTextContent('loading');
      
      // Resolve userinfo
      resolveUserInfo(mockUser);
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      expect(screen.getByTestId('authenticated')).toHaveTextContent('yes');
    });
  });

  describe('Error Handling', () => {
    it('handles userinfo fetch errors gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      localStorage.setItem('access_token', 'bad-token');
      get.mockRejectedValueOnce(new Error('Network error'));
      
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>
      );
      
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('ready');
      });
      
      expect(consoleSpy).toHaveBeenCalledWith('[AuthProvider] /auth/userinfo FAILED:', expect.any(Error));
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no');
      
      consoleSpy.mockRestore();
    });
  });
});
