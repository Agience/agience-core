import { useContext } from "react";
import { WorkspacesContext } from "../context/workspaces/WorkspacesContext";

export const useWorkspaces = () => {
  const context = useContext(WorkspacesContext);
  if (!context) throw new Error('useWorkspaces must be used within a WorkspacesProvider');
  return context;
};