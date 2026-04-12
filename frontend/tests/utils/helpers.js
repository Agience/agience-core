/**
 * Shared test helpers for frontend tests
 */

// Mock factories for API responses

export function mockWorkspace(overrides = {}) {
  return {
    id: 'w1',
    name: 'Test Workspace',
    description: 'Test description',
    created_by: 'user-123',
    created_time: '2024-01-01T00:00:00Z',
    modified_time: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockArtifact(overrides = {}) {
  return {
    id: 'c1',
    collection_id: 'w1',
    state: 'draft',
    context: '{}',
    content: 'test content',
    order_key: 'U',
    created_time: '2024-01-01T00:00:00Z',
    modified_time: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockCollection(overrides = {}) {
  return {
    id: 'col1',
    name: 'Test Collection',
    description: 'Test description',
    created_by: 'user-123',
    created_time: '2024-01-01T00:00:00Z',
    modified_time: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockCollectionArtifact(overrides = {}) {
  return {
    id: 'v1',
    root_id: 'r1',
    context: '{}',
    content: 'test content',
    is_archived: false,
    created_by: 'user-123',
    created_time: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockShare(overrides = {}) {
  return {
    id: 's1',
    collection_id: 'col1',
    name: 'Test Share',
    key: 'k-abc123',
    can_read: true,
    can_write: false,
    read_requires_identity: false,
    write_requires_identity: true,
    created_time: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockPerson(overrides = {}) {
  return {
    id: 'user-123',
    email: 'test@example.com',
    name: 'Test User',
    picture: 'https://example.com/avatar.png',
    ...overrides,
  };
}

export function mockSearchResult(overrides = {}) {
  return {
    hits: [
      {
        id: 'h1',
        score: 1.5,
        root_id: 'r1',
        version_id: 'v1',
        collection_id: 'w1',
      },
    ],
    total: 1,
    query_text: 'test',
    used_hybrid: false,
    from: 0,
    size: 20,
    ...overrides,
  };
}

// Test setup helpers

export function setupApiMocks(api) {
  // Reset all mocks
  if (api.get && api.get.mockReset) api.get.mockReset();
  if (api.post && api.post.mockReset) api.post.mockReset();
  if (api.patch && api.patch.mockReset) api.patch.mockReset();
  if (api.del && api.del.mockReset) api.del.mockReset();
  if (api.put && api.put.mockReset) api.put.mockReset();
}

// Assertion helpers

export function assertHasFields(obj, fields) {
  fields.forEach((field) => {
    if (!(field in obj)) {
      throw new Error(`Object missing field: ${field}`);
    }
  });
}

export function assertMatchesShape(obj, shape) {
  Object.keys(shape).forEach((key) => {
    if (obj[key] !== shape[key]) {
      throw new Error(
        `Field ${key}: expected ${shape[key]}, got ${obj[key]}`
      );
    }
  });
}

// Local storage mocking

export function mockLocalStorage() {
  const store = {};
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => {
      store[key] = value.toString();
    },
    removeItem: (key) => {
      delete store[key];
    },
    clear: () => {
      Object.keys(store).forEach((key) => delete store[key]);
    },
  };
}
