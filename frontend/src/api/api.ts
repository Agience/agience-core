// frontend/src/api/api.ts
import axios from 'axios';
import { getRuntimeConfig } from '../config/runtime';

// Base URL for all API calls
const BACKEND_URI = getRuntimeConfig().backendUri;

const api = axios.create({
  baseURL: BACKEND_URI || 'http://localhost:8081',
  timeout: 10000, // 10s — prevents indefinite hangs on server disconnect
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach Bearer token from localStorage.
api.interceptors.request.use(config => {
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
      const isAuthEndpoint = url.startsWith('/auth/password/') || url.startsWith('/auth/otp/');
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

// x-www-form-urlencoded helper; always prefix BACKEND_URI
export async function postForm<T>(
  url: string,
  body: URLSearchParams
): Promise<T> {
  const res = await fetch(`${BACKEND_URI}${url}`, {
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
