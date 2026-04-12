// frontend/src/api/types/stream.ts

export interface StreamSession {
  stream: string;
  source_artifact_id: string;
  artifact_id: string;
  workspace_id: string;
  status: 'live';
}

export interface StreamSessionsResponse {
  count: number;
  sessions: StreamSession[];
}
