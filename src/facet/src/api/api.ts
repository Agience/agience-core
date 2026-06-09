// facet/src/api/api.ts
import axios from 'axios';
import { getRuntimeConfig } from '../config/runtime';

// Base URLs. After the four-container split (Step 1.1a-ii), Origin owns identity
// and Mantle owns artifacts. A single axios instance is kept; the request
// interceptor rewrites baseURL to ORIGIN_URI for /auth/* calls (excluding
// /auth/passkey/*, /auth/otp/*, /auth/authorizer/* which stay on Mantle until
// 1.1b/1.1e move them).
const MANTLE_URI = getRuntimeConfig().mantleUri;
const ORIGIN_URI = getRuntimeConfig().originUri;

const api = axios.create({
  baseURL: MANTLE_URI || 'http://localhost:8081',
  timeout: 10000, // 10s — prevents indefinite hangs on server disconnect
  headers: {
    'Content-Type': 'application/json',
  },
});

function isOriginAuthPath(url: string): boolean {
  // /auth/* — owned by Origin except `/auth/authorizer/*` which stays Mantle-side.
  if (url.startsWith('/auth/')) {
    if (url.startsWith('/auth/authorizer/')) return false;
    return true;
  }
  // /api-keys/* — moved to Origin in 1.1c.
  if (url.startsWith('/api-keys') || url === '/api-keys') return true;
  // /server-credentials/* CRUD — moved to Origin in 1.1c. The lone JWK PUT
  // endpoint stays on Mantle but isn't called from the browser, only from
  // server-side code at startup.
  if (url.startsWith('/server-credentials') || url === '/server-credentials') return true;
  // /grants/* — moved to Origin in 1.1d.
  if (url.startsWith('/grants') || url === '/grants') return true;
  // /setup/* and /platform/* — moved to Origin in 1.1e.
  if (url.startsWith('/setup') || url === '/setup') return true;
  if (url.startsWith('/platform') || url === '/platform') return true;
  return false;
}

// Route /auth/* (minus the carve-outs) to Origin.
api.interceptors.request.use(config => {
  const url = config.url || '';
  if (isOriginAuthPath(url)) {
    config.baseURL = ORIGIN_URI;
  }
  const token = localStorage.getItem('access_token');
  if (token && config.headers) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401, clear token and redirect to login
api.interceptors.response.use(
  response => response,
  error => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't intercept 401s from auth endpoints — let the Login page handle them.
      const url = originalRequest?.url || '';
      const isAuthEndpoint =
        url.startsWith('/auth/password/') ||
        url.startsWith('/auth/otp/') ||
        url.startsWith('/auth/passkey/');
      if (!isAuthEndpoint) {
        originalRequest._retry = true;
        localStorage.removeItem('access_token');
        window.location.href = '/login';
      }
    }
    // On 402 (Payment Required), dispatch upgrade prompt event
    if (error.response?.status === 402) {
      const reason = error.response.headers?.['x-upgrade-reason'] || 'limit_reached';
      const detail = error.response.data?.detail;
      window.dispatchEvent(
        new CustomEvent('agience:upgrade-prompt', {
          detail: {
            reason,
            code: typeof detail === 'object' ? detail?.code : undefined,
            limit: typeof detail === 'object' ? detail?.limit : undefined,
            used: typeof detail === 'object' ? detail?.used : undefined,
          },
        }),
      );
    }
    return Promise.reject(error);
  }
);

// Typed helpers using simple config type
export async function get<T>(
  url: string,
  config?: Record<string, unknown>
): Promise<T> {
  const res = await api.get<T>(url, config);
  return res.data;
}

export async function post<T, B = unknown>(
  url: string,
  body?: B,
  config?: Record<string, unknown>
): Promise<T> {
  const res = await api.post<T>(url, body, config);
  return res.data;
}

export async function put<T, B = unknown>(
  url: string,
  body?: B,
  config?: Record<string, unknown>
): Promise<T> {
  const res = await api.put<T>(url, body, config);
  return res.data;
}

export async function patch<T, B = unknown>(
  url: string,
  body?: B,
  config?: Record<string, unknown>
): Promise<T> {
  const res = await api.patch<T>(url, body, config);
  return res.data;
}

export async function del<T>(
  url: string,
  config?: Record<string, unknown>
): Promise<T> {
  const res = await api.delete<T>(url, config);
  return res.data;
}

// x-www-form-urlencoded helper. Honors the same Origin / Mantle split as the
// axios interceptor above — /auth/* goes to ORIGIN_URI (with the same carve-outs).
export async function postForm<T>(
  url: string,
  body: URLSearchParams
): Promise<T> {
  const baseUri = isOriginAuthPath(url) ? ORIGIN_URI : MANTLE_URI;
  const res = await fetch(`${baseUri}${url}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({} as { detail?: string }));
    throw new Error(err.detail ?? 'Request failed');
  }

  return res.json() as Promise<T>;
}

export default api;
