// src/contexts/workspace/workspace.types.ts
import { WorkspaceResponse } from "../../api/types/workspace";
import { ArtifactResponse } from "../../api/types/artifact";

export type CreateWorkspaceInput = { name: string; description?: string };

export type Workspace = WorkspaceResponse;
export type Artifact = ArtifactResponse;
