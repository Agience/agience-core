// src/api/types/workspace.ts

export interface WorkspaceCreate {
  name: string;
  description: string;
}

export interface WorkspaceResponse {
  id: string;
  name: string;
  description: string;
  created_by: string;
  created_time: string;
  modified_time: string;
  context?: Record<string, unknown>;
  order_key?: string;
}

export interface WorkspaceUpdate {
  name?: string;
  description?: string;
}

export type Workspace = WorkspaceResponse;