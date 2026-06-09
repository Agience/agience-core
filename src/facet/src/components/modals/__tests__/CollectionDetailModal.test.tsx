import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import CollectionDetailModal from '../CollectionDetailModal';

const listCollectionsMock = vi.fn();
const listGrantsMock = vi.fn();
const listCollectionCommitsMock = vi.fn();

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'user-1' },
  }),
}));

vi.mock('@/api/collections', () => ({
  listCollections: (...args: unknown[]) => listCollectionsMock(...args),
  listGrants: (...args: unknown[]) => listGrantsMock(...args),
  listCollectionCommits: (...args: unknown[]) => listCollectionCommitsMock(...args),
  createCollection: vi.fn(),
  updateCollection: vi.fn(),
  deleteCollection: vi.fn(),
  createGrant: vi.fn(),
  updateGrant: vi.fn(),
  deleteGrant: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('CollectionDetailModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    listCollectionsMock.mockResolvedValue([
      {
        id: 'col-1',
        name: 'Main Collection',
        description: 'Primary collection',
        created_by: 'user-1',
        created_time: '2026-03-21T00:00:00Z',
        modified_time: '2026-03-21T00:00:00Z',
      },
    ]);
    listGrantsMock.mockResolvedValue([]);
  });

  it('renders commit history rows with formatted provenance', async () => {
    listCollectionCommitsMock.mockResolvedValue([
      {
        id: 'cm-1',
        message: 'Initial import',
        author_id: 'user-1',
        presenter_id: 'agent-42',
        confirmation: 'human_affirmed',
        changeset_type: 'automation',
        timestamp: '2026-03-21T10:30:00Z',
        item_ids: [],
      },
    ]);

    render(<CollectionDetailModal open onClose={vi.fn()} />);

    expect(await screen.findByText('Commit History')).toBeInTheDocument();
    expect(screen.getByText('Initial import')).toBeInTheDocument();
    expect(screen.getByText('agent-42')).toBeInTheDocument();
    expect(screen.getByText('Human Affirmed / Automation')).toBeInTheDocument();

    await waitFor(() => {
      expect(listCollectionCommitsMock).toHaveBeenCalledWith('col-1');
    });
  });

  it('shows empty commit-history state when there are no commits', async () => {
    listCollectionCommitsMock.mockResolvedValue([]);

    render(<CollectionDetailModal open onClose={vi.fn()} />);

    expect(await screen.findByText('Commit History')).toBeInTheDocument();
    expect(screen.getByText('No commits recorded yet.')).toBeInTheDocument();
  });
});
