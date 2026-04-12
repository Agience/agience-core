/**
 * Tests for CollectionsProvider.
 *
 * Covers:
 *   - Loads collections when authenticated
 *   - Does not load when unauthenticated (and no grant keys stored)
 *   - Loads when grant keys are present in storage even if unauthenticated
 *   - isLoading flips false after fetch (success + failure)
 *   - addSharedCollection appends to state
 *   - addSharedCollection swallows errors without corrupting state
 *   - Edit modal open/close
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, cleanup } from '@testing-library/react';

import { CollectionsProvider } from '../CollectionsProvider';
import { useCollections } from '../CollectionsContext';

// ---- Mocks ----

const listCollectionsMock = vi.fn();
const createCollectionMock = vi.fn();

vi.mock('../../../api/collections', () => ({
  listCollections: (...args: unknown[]) => listCollectionsMock(...args),
  createCollection: (...args: unknown[]) => createCollectionMock(...args),
}));

const { useAuthMock } = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
}));

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => useAuthMock(),
}));

// ---- Harness ----

function Probe() {
  const ctx = useCollections();
  return (
    <div>
      <div data-testid="loading">{String(ctx.isLoading)}</div>
      <div data-testid="count">{ctx.collections.length}</div>
      <div data-testid="names">
        {ctx.collections.map((c) => c.name).join(',')}
      </div>
      <div data-testid="edit-open">{String(ctx.isEditModalOpen)}</div>
      <button onClick={() => ctx.addSharedCollection('NewOne')}>add</button>
      <button onClick={() => ctx.openEditModal()}>open</button>
      <button onClick={() => ctx.closeEditModal()}>close</button>
    </div>
  );
}

function renderWithProvider() {
  return render(
    <CollectionsProvider>
      <Probe />
    </CollectionsProvider>,
  );
}

describe('CollectionsProvider', () => {
  beforeEach(() => {
    listCollectionsMock.mockReset();
    createCollectionMock.mockReset();
    useAuthMock.mockReset();
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it('fetches collections when authenticated', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, loading: false });
    listCollectionsMock.mockResolvedValue([
      { id: 'c-1', name: 'First', created_by: 'u-1' },
      { id: 'c-2', name: 'Second', created_by: 'u-1' },
    ]);

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('count').textContent).toBe('2');
    expect(screen.getByTestId('names').textContent).toBe('First,Second');
    expect(listCollectionsMock).toHaveBeenCalledTimes(1);
  });

  it('does not fetch when auth is still loading', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, loading: true });
    renderWithProvider();
    // Give the effect a chance to run.
    await new Promise((r) => setTimeout(r, 10));
    expect(listCollectionsMock).not.toHaveBeenCalled();
  });

  it('does not fetch when unauthenticated and no grant keys stored', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, loading: false });
    renderWithProvider();
    await new Promise((r) => setTimeout(r, 10));
    expect(listCollectionsMock).not.toHaveBeenCalled();
  });

  it('fetches when grant keys present even if unauthenticated', async () => {
    sessionStorage.setItem('grant_keys', JSON.stringify(['gk-1']));
    useAuthMock.mockReturnValue({ isAuthenticated: false, loading: false });
    listCollectionsMock.mockResolvedValue([]);

    renderWithProvider();

    await waitFor(() => expect(listCollectionsMock).toHaveBeenCalled());
  });

  it('flips isLoading false when fetch fails', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, loading: false });
    listCollectionsMock.mockRejectedValue(new Error('boom'));
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('count').textContent).toBe('0');
    errSpy.mockRestore();
  });

  it('addSharedCollection appends on success', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, loading: false });
    listCollectionsMock.mockResolvedValue([]);
    createCollectionMock.mockResolvedValue({
      id: 'c-new',
      name: 'NewOne',
      created_by: 'u-1',
    });

    renderWithProvider();

    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false'),
    );

    await act(async () => {
      screen.getByText('add').click();
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(createCollectionMock).toHaveBeenCalledWith({ name: 'NewOne' });
    await waitFor(() =>
      expect(screen.getByTestId('names').textContent).toBe('NewOne'),
    );
  });

  it('addSharedCollection swallows errors and leaves state unchanged', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, loading: false });
    listCollectionsMock.mockResolvedValue([]);
    createCollectionMock.mockRejectedValue(new Error('no'));
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderWithProvider();
    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false'),
    );

    await act(async () => {
      screen.getByText('add').click();
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(screen.getByTestId('count').textContent).toBe('0');
    errSpy.mockRestore();
  });

  it('openEditModal / closeEditModal toggle the flag', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, loading: false });
    listCollectionsMock.mockResolvedValue([]);

    renderWithProvider();
    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false'),
    );

    act(() => {
      screen.getByText('open').click();
    });
    expect(screen.getByTestId('edit-open').textContent).toBe('true');

    act(() => {
      screen.getByText('close').click();
    });
    expect(screen.getByTestId('edit-open').textContent).toBe('false');
  });

  it('malformed grant_keys JSON is ignored', async () => {
    sessionStorage.setItem('grant_keys', 'not-json');
    useAuthMock.mockReturnValue({ isAuthenticated: false, loading: false });
    renderWithProvider();
    await new Promise((r) => setTimeout(r, 10));
    expect(listCollectionsMock).not.toHaveBeenCalled();
  });

  it('empty grant_keys array does not count as "has keys"', async () => {
    sessionStorage.setItem('grant_keys', JSON.stringify([]));
    useAuthMock.mockReturnValue({ isAuthenticated: false, loading: false });
    renderWithProvider();
    await new Promise((r) => setTimeout(r, 10));
    expect(listCollectionsMock).not.toHaveBeenCalled();
  });
});
