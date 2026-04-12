import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CommitReviewDialog } from '../CommitReviewDialog';
import type { WorkspaceCommitResponse } from '@/api/types/workspace_commit';
import type { Artifact } from '@/context/workspace/workspace.types';

vi.mock('@/context/collections/CollectionsContext', () => ({
  useCollections: () => ({
    collections: [],
  }),
}));

describe('CommitReviewDialog', () => {
  it('hides artifacts without changes from the review list', async () => {
    const artifacts: Artifact[] = [
      {
        id: 'artifact-1',
        context: JSON.stringify({ title: 'No change artifact' }),
        content: 'Static content',
        state: 'committed',
        collection_id: undefined,
      },
      {
        id: 'artifact-2',
        context: JSON.stringify({ title: 'Updated artifact' }),
        content: 'Updated content',
        state: 'committed',
        collection_id: undefined,
      },
    ];

    const preview: WorkspaceCommitResponse = {
      workspace_id: 'ws-1',
      plan: {
        artifacts: [
          {
            artifact_id: 'artifact-1',
            action: 'noop',
            target_collections: [],
            committed_collections: [],
            adds: [],
            removes: [],
            blocked_adds: [],
            blocked_removes: [],
          },
          {
            artifact_id: 'artifact-2',
            action: 'commit',
            target_collections: [],
            committed_collections: [],
            adds: ['collection-1'],
            removes: [],
            blocked_adds: [],
            blocked_removes: [],
          },
        ],
        collections: [
          {
            collection_id: 'collection-1',
            added_artifacts: ['artifact-9'],
            removed_artifacts: [],
            blocked_adds: [],
            blocked_removes: [],
          },
        ],
        warnings: [],
        total_artifacts: 1,
        total_adds: 1,
        total_removes: 0,
        blocked_collections: [],
      },
      dry_run: true,
      updated_workspace_artifacts: [],
      deleted_workspace_artifact_ids: [],
      skipped_workspace_artifact_ids: [],
      per_collection: [],
    };

    render(
      <CommitReviewDialog
        open
        onOpenChange={vi.fn()}
        preview={preview}
        isLoading={false}
        isCommitting={false}
        onRefresh={vi.fn()}
        onPublish={vi.fn()}
        artifacts={artifacts}
        selectedArtifactIds={['artifact-1', 'artifact-2']}
        onToggleArtifact={vi.fn()}
        onSelectAll={vi.fn()}
        onClearSelection={vi.fn()}
      />
    );

    expect(await screen.findByText('Updated artifact')).toBeInTheDocument();
    expect(screen.queryByText('No change artifact')).toBeNull();
    expect(screen.getByText('Publish 1 change')).toBeInTheDocument();
  });

  it('shows provenance summary when per-collection metadata is present', async () => {
    const artifacts: Artifact[] = [
      {
        id: 'artifact-9',
        context: JSON.stringify({ title: 'Artifact with provenance' }),
        content: 'Some content',
        state: 'committed',
        collection_id: undefined,
      },
    ];

    const preview: WorkspaceCommitResponse = {
      workspace_id: 'ws-1',
      plan: {
        artifacts: [
          {
            artifact_id: 'artifact-9',
            action: 'commit',
            target_collections: ['collection-1'],
            committed_collections: [],
            adds: ['collection-1'],
            removes: [],
            blocked_adds: [],
            blocked_removes: [],
          },
        ],
        collections: [
          {
            collection_id: 'collection-1',
            added_artifacts: ['artifact-9'],
            removed_artifacts: [],
            blocked_adds: [],
            blocked_removes: [],
          },
        ],
        warnings: [],
        total_artifacts: 1,
        total_adds: 1,
        total_removes: 0,
        blocked_collections: [],
      },
      dry_run: true,
      updated_workspace_artifacts: [],
      deleted_workspace_artifact_ids: [],
      skipped_workspace_artifact_ids: [],
      per_collection: [
        {
          collection_id: 'collection-1',
          commit_id: 'cm-1',
          adds: ['v1'],
          removes: [],
          confirmation: 'human_affirmed',
          changeset_type: 'manual',
        },
      ],
    };

    render(
      <CommitReviewDialog
        open
        onOpenChange={vi.fn()}
        preview={preview}
        isLoading={false}
        isCommitting={false}
        onRefresh={vi.fn()}
        onPublish={vi.fn()}
        artifacts={artifacts}
        selectedArtifactIds={['artifact-9']}
        onToggleArtifact={vi.fn()}
        onSelectAll={vi.fn()}
        onClearSelection={vi.fn()}
      />
    );

    expect(await screen.findByText('Provenance')).toBeInTheDocument();
    expect(screen.getAllByText('Human Affirmed').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Manual').length).toBeGreaterThan(0);
    expect(screen.getByTestId('collection-provenance-collection-1')).toHaveTextContent('Collection provenance: Human Affirmed / Manual');
  });
});
