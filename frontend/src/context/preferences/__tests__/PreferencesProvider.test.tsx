/**
 * Tests for PreferencesProvider.
 *
 * Covers:
 *   - Loads preferences on mount when authenticated
 *   - Skips load when unauthenticated (flips isLoading false)
 *   - API failure on initial load leaves preferences empty, isLoading false
 *   - updatePreferences merges optimistically, replaces with backend response
 *   - updatePreferences deep-merges nested objects
 *   - updatePreferences failure reloads from backend to restore consistency
 *   - updatePreferences failure + reload failure leaves state as-is without throwing
 */

import { useContext } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, cleanup } from '@testing-library/react';

import { PreferencesProvider } from '../PreferencesProvider';
import { PreferencesContext } from '../PreferencesContext';

// ---- Mocks ----

const getPreferencesMock = vi.fn();
const updatePreferencesMock = vi.fn();

vi.mock('../../../api/preferences', () => ({
  getPreferences: (...args: unknown[]) => getPreferencesMock(...args),
  updatePreferences: (...args: unknown[]) => updatePreferencesMock(...args),
}));

const { useAuthMock } = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
}));

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => useAuthMock(),
}));

// ---- Harness ----

function Probe() {
  const ctx = useContext(PreferencesContext);
  if (!ctx) return <div data-testid="no-ctx">no ctx</div>;
  return (
    <div>
      <div data-testid="loading">{String(ctx.isLoading)}</div>
      <div data-testid="prefs">{JSON.stringify(ctx.preferences)}</div>
      <button
        onClick={() =>
          ctx.updatePreferences({ theme: 'dark' } as Record<string, unknown>)
        }
      >
        set-theme
      </button>
      <button
        onClick={() =>
          ctx.updatePreferences({ layout: { density: 'compact' } } as Record<
            string,
            unknown
          >)
        }
      >
        set-layout
      </button>
    </div>
  );
}

function renderWithProvider() {
  return render(
    <PreferencesProvider>
      <Probe />
    </PreferencesProvider>,
  );
}

describe('PreferencesProvider', () => {
  beforeEach(() => {
    getPreferencesMock.mockReset();
    updatePreferencesMock.mockReset();
    useAuthMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('loads preferences when authenticated', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    getPreferencesMock.mockResolvedValue({ theme: 'light' });

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(JSON.parse(screen.getByTestId('prefs').textContent!)).toEqual({
      theme: 'light',
    });
  });

  it('skips load and flips isLoading false when unauthenticated', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false });

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(getPreferencesMock).not.toHaveBeenCalled();
  });

  it('initial load failure leaves prefs empty and not loading', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    getPreferencesMock.mockRejectedValue(new Error('down'));
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(JSON.parse(screen.getByTestId('prefs').textContent!)).toEqual({});
    errSpy.mockRestore();
  });

  it('updatePreferences replaces state with backend response on success', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    getPreferencesMock.mockResolvedValue({ theme: 'light' });
    updatePreferencesMock.mockResolvedValue({
      theme: 'dark',
      locale: 'en-US',
    });

    renderWithProvider();
    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false'),
    );

    await act(async () => {
      screen.getByText('set-theme').click();
      await new Promise((r) => setTimeout(r, 0));
    });

    await waitFor(() => {
      expect(
        JSON.parse(screen.getByTestId('prefs').textContent!),
      ).toEqual({ theme: 'dark', locale: 'en-US' });
    });
  });

  it('updatePreferences deep-merges nested objects optimistically', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    getPreferencesMock.mockResolvedValue({
      layout: { sidebar: 'open' },
    });
    // Never resolve so the optimistic state sticks around.
    updatePreferencesMock.mockImplementation(() => new Promise(() => {}));

    renderWithProvider();
    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false'),
    );

    await act(async () => {
      screen.getByText('set-layout').click();
      await new Promise((r) => setTimeout(r, 0));
    });

    const prefs = JSON.parse(screen.getByTestId('prefs').textContent!);
    expect(prefs.layout).toEqual({ sidebar: 'open', density: 'compact' });
  });

  it('updatePreferences failure reloads preferences from backend', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    getPreferencesMock
      .mockResolvedValueOnce({ theme: 'light' })
      // Second call (after update failure): returns canonical state
      .mockResolvedValueOnce({ theme: 'light' });
    updatePreferencesMock.mockRejectedValue(new Error('conflict'));
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderWithProvider();
    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false'),
    );

    await act(async () => {
      screen.getByText('set-theme').click();
      await new Promise((r) => setTimeout(r, 0));
    });

    await waitFor(() => {
      expect(getPreferencesMock).toHaveBeenCalledTimes(2);
    });
    // Reloaded canonical state wins.
    expect(
      JSON.parse(screen.getByTestId('prefs').textContent!),
    ).toEqual({ theme: 'light' });
    errSpy.mockRestore();
  });

  it('update failure + reload failure does not crash', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    getPreferencesMock
      .mockResolvedValueOnce({ theme: 'light' })
      .mockRejectedValueOnce(new Error('still down'));
    updatePreferencesMock.mockRejectedValue(new Error('conflict'));
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderWithProvider();
    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false'),
    );

    await act(async () => {
      screen.getByText('set-theme').click();
      await new Promise((r) => setTimeout(r, 0));
    });

    // Still mounted, still rendering (smoke test).
    expect(screen.getByTestId('loading').textContent).toBe('false');
    errSpy.mockRestore();
  });
});
