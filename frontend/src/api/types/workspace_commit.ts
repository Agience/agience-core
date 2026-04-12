// src/api/types/workspace_commit.ts
import type { ArtifactResponse } from './artifact';

export type ArtifactCommitAction =
  | 'commit'
  | 'noop'
  | 'skipped';

export interface WorkspaceCommitRequest {
  artifact_ids?: string[];
  dry_run?: boolean;
  commit_token?: string;
}

export interface CollectionCommitSummary {
  collection_id: string;
  commit_id?: string | null;
  adds: string[];
  removes: string[];
  confirmation?: string | null;
  changeset_type?: string | null;
}

export interface CollectionChangeSummary {
  collection_id: string;
  added_artifacts: string[];
  removed_artifacts: string[];
  blocked_adds: string[];
  blocked_removes: string[];
}

export interface ArtifactCommitChange {
  artifact_id: string;
  root_id?: string | null;
  action: ArtifactCommitAction;
  state_before?: ArtifactResponse['state'] | 'deleted' | null;
  state_after?: ArtifactResponse['state'] | 'deleted' | null;
  target_collections: string[];
  committed_collections: string[];
  adds: string[];
  removes: string[];
  blocked_adds: string[];
  blocked_removes: string[];
  skipped_reason?: string | null;
}

export interface CommitWarning {
  code: string;
  message: string;
  artifact_id?: string | null;
  kind?: string | null;
}

export interface WorkspaceCommitPlanSummary {
  artifacts: ArtifactCommitChange[];
  collections: CollectionChangeSummary[];
  warnings?: CommitWarning[];
  total_artifacts: number;
  total_adds: number;
  total_removes: number;
  blocked_collections: string[];
}

export interface WorkspaceCommitResponse {
  workspace_id: string;
  plan: WorkspaceCommitPlanSummary;
  dry_run: boolean;
  commit_token?: string | null;
  updated_workspace_artifacts: ArtifactResponse[];
  deleted_workspace_artifact_ids: string[];
  skipped_workspace_artifact_ids: string[];
  per_collection: CollectionCommitSummary[];
}

export type WorkspaceCommitPreviewResponse = WorkspaceCommitResponse;
