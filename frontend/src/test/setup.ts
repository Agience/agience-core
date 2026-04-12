import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Reset DOM between tests to avoid cross-test pollution.
afterEach(() => {
  cleanup();

  // Defensive: ensure suites don't leak fake timers.
  // Leaked fake timers can cause Vitest to hang or exit non-zero even
  // when all assertions passed.
  try {
    vi.clearAllTimers();
  } catch {
    // ignore
  }
  try {
    vi.useRealTimers();
  } catch {
    // ignore
  }
});
