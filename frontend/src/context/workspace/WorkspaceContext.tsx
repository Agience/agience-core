// src/context/workspace/WorkspaceContext.tsx
import { createStrictContext } from '../../utils/createStrictContext';
import { MouseEvent } from 'react';
import { Artifact } from './workspace.types';
import { ArtifactCreate } from '../../api/types';
import type {
  WorkspaceCommitRequest,
  WorkspaceCommitResponse,
} from '../../api/types/workspace_commit';


export interface WorkspaceContextType {
  artifacts: Artifact[];
  /** Currently displayed artifacts in the center panel (may be workspace, collection, or search results) */
  displayedArtifacts?: Artifact[];
  /** Setter for displayed artifacts so components like Browser can publish what is currently shown */
  setDisplayedArtifacts?: (artifacts: Artifact[]) => void;
  selectedArtifactIds: string[];
  isCommitting: boolean;
  addArtifact: (artifact: ArtifactCreate) => Promise<void>;
  addExistingArtifact: (artifact: Artifact) => void;
  createArtifact: (artifact: ArtifactCreate, insertIndex?: number) => Promise<Artifact | null>;
  updateArtifact: (artifact: Partial<Artifact>) => Promise<void>;
  removeArtifact: (id: string) => Promise<void>;
  revertArtifact: (id: string) => Promise<void>;
  refreshArtifacts: (workspaceId: string) => Promise<void>;
  selectArtifact: (id: string, event: MouseEvent) => void;
  orderArtifacts: (orderedIds: string[]) => Promise<void>;
  /** Import collection-root artifacts into the active workspace and insert at a drop index */
  importArtifactsByRootIds: (rootIds: string[], insertIndex: number) => Promise<void>;
  selectAllArtifacts: () => void;
  unselectAllArtifacts: () => void;
  commitCurrentWorkspace: (input?: WorkspaceCommitRequest) => void;
  commitPreview: WorkspaceCommitResponse | null;
  fetchCommitPreview: (
    input?: WorkspaceCommitRequest
  ) => Promise<WorkspaceCommitResponse | null>;
  clearCommitPreview: () => void;
  extractInformationFromArtifact: (sourceArtifactId: string, contextArtifactIds?: string[]) => Promise<void>;
  extractInformationFromSelection: (options?: { sourceArtifactId?: string }) => Promise<void>;
  createNewArtifact: () => void;
  registerNewArtifactHandler: (fn: (artifact: Artifact) => void) => void;  
}

export const [WorkspaceContext, useWorkspace] =
  createStrictContext<WorkspaceContextType>('WorkspaceContext');
