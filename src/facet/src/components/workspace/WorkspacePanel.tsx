/**
 * WorkspacePanel
 *
 * Right panel in the two-panel layout. Houses the active workspace's artifact
 * browser and all list-management UI.
 *
 * Phase 1: thin structural wrapper around the existing Browser component.
 * The complex state (upload, filter, commit review) stays in Browser for
 * now and will be lifted here once Browser is slimmed down.
 *
 * Replaces: WorkspaceShell → Browser stacking from the old layout.
 */
import Browser from '../browser/Browser';
import type { ActiveSource } from '../../types/workspace';
import type { Artifact } from '../../context/workspace/workspace.types';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface WorkspacePanelProps {
  activeSource: ActiveSource;
  selectedArtifactId?: string | null;
  searchResultArtifacts?: Artifact[];
  onArtifactSelect?: (artifactId: string | null) => void;
  onOpenArtifact?: (artifact: Artifact, options?: { startInEditMode?: boolean }) => void;
  onAssignCollections?: (artifactId: string) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function WorkspacePanel({
  activeSource,
  selectedArtifactId,
  searchResultArtifacts,
  onArtifactSelect,
  onOpenArtifact,
  onAssignCollections,
}: WorkspacePanelProps) {
  return (
    <div className="flex flex-col h-full">
      <Browser
        activeSource={activeSource}
        selectedArtifactId={selectedArtifactId ?? undefined}
        searchResultArtifacts={searchResultArtifacts}
        onArtifactSelect={onArtifactSelect}
        onOpenArtifact={onOpenArtifact}
        onAssignCollections={onAssignCollections}
      />
    </div>
  );
}

export default WorkspacePanel;
