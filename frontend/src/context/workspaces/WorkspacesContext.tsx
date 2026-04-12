// src/contexts/workspace/WorkspacesContext.tsx
import { createStrictContext } from '../../utils/createStrictContext';
import { Workspace } from '../workspace/workspace.types';

export interface WorkspacesContextType {
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  activeWorkspaceId: string | null;  
  createWorkspace: (name: string, description: string, options?: { activate?: boolean }) => Promise<Workspace>;  
  updateWorkspace: (workspace: Partial<Workspace> & { id: string }) => Promise<void>;
  deleteWorkspace: (id: string) => Promise<void>;
  setActiveWorkspaceId: (id: string | null) => void;
}

export const [WorkspacesContext, useWorkspaces] =
  createStrictContext<WorkspacesContextType>('WorkspacesContext');
