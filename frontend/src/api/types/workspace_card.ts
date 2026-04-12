export interface ArtifactKeyResponse {
  workspace_id: string;
  artifact_id: string;
  key_id: string;
  /** Returned once — never stored server-side. Display immediately and discard. */
  key: string;
}