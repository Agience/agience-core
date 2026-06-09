import { vi } from 'vitest';

export function mockApiModule() {
  const calls = [];
  vi.doMock('../src/api/api', () => {
    return {
      __esModule: true,
      default: {
        post: vi.fn((url, body) => {
          calls.push({ method: 'post', url, body });
          return Promise.resolve({ data: {} });
        }),
        get: vi.fn((url, config) => {
          calls.push({ method: 'get', url, config });
          return Promise.resolve({ data: {} });
        }),
        patch: vi.fn((url, body) => {
          calls.push({ method: 'patch', url, body });
          return Promise.resolve({ data: {} });
        }),
        put: vi.fn((url, body) => {
          calls.push({ method: 'put', url, body });
          return Promise.resolve({ data: {} });
        }),
        delete: vi.fn((url, config) => {
          calls.push({ method: 'delete', url, config });
          return Promise.resolve({ data: {} });
        }),
      },
      get: vi.fn((url, config) => {
        calls.push({ method: 'get', url, config });
        return Promise.resolve({ data: {} });
      }),
      post: vi.fn((url, body) => {
        calls.push({ method: 'post', url, body });
        return Promise.resolve({ data: {} });
      }),
      patch: vi.fn((url, body) => {
        calls.push({ method: 'patch', url, body });
        return Promise.resolve({ data: {} });
      }),
      del: vi.fn((url, config) => {
        calls.push({ method: 'del', url, config });
        return Promise.resolve({ data: {} });
      }),
    };
  });
  return {
    getCalls: () => calls,
  };
}
