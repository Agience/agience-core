import { useMemo, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Loader2, AlertTriangle, Plus, Minus, ChevronDown, ChevronRight } from 'lucide-react';
import { CollectionChip } from '@/components/common/CollectionChip';
import type { WorkspaceCommitResponse, ArtifactCommitChange, CommitWarning } from '@/api/types/workspace_commit';
import type { Artifact } from '@/context/workspace/workspace.types';
import { useCollections } from '@/context/collections/CollectionsContext';
import { BlockedState, EmptyState, LoadingState } from '@/components/common/states';
import { formatProvenanceLabel } from '@/utils/provenance';

interface CommitReviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: WorkspaceCommitResponse | null;
  isLoading: boolean;
  isCommitting: boolean;
  onRefresh: () => void;
  onPublish: () => void;
  artifacts: Artifact[];
  selectedArtifactIds: string[];
  onToggleArtifact: (artifactId: string) => void;
  onSelectAll: () => void;
  onClearSelection: () => void;
}

export function CommitReviewDialog({
  open,
  onOpenChange,
  preview,
  isLoading,
  isCommitting,
  onRefresh,
  onPublish,
  artifacts,
  selectedArtifactIds,
  onToggleArtifact,
  onSelectAll,
  onClearSelection,
}: CommitReviewDialogProps) {
  const [expandedArtifacts, setExpandedArtifacts] = useState<Set<string>>(new Set());
  const { collections } = useCollections();

  const collectionNameById = useMemo(() => {
    const map = new Map<string, string>();
    collections.forEach(collection => {
      if (collection.name) {
        map.set(collection.id, collection.name);
      }
    });
    return map;
  }, [collections]);
  
  const artifactIndex = useMemo(() => {
    const index = new Map<string, Artifact>();
    artifacts.forEach(artifact => {
      const id = artifact.id ? String(artifact.id) : undefined;
      if (id) index.set(id, artifact);
    });
    return index;
  }, [artifacts]);

  const planArtifacts = useMemo(() => preview?.plan.artifacts ?? [], [preview?.plan.artifacts]);
  const visiblePlanArtifacts = useMemo(
    () => planArtifacts.filter(artifact => artifact.action !== 'noop'),
    [planArtifacts]
  );
  const planCollections = useMemo(() => preview?.plan.collections ?? [], [preview?.plan.collections]);
  const blockedCollections = useMemo(() => preview?.plan.blocked_collections ?? [], [preview?.plan.blocked_collections]);
  const planWarnings = useMemo(() => preview?.plan.warnings ?? [], [preview?.plan.warnings]);
  const warningsByArtifactId = useMemo(() => {
    const map = new Map<string, CommitWarning[]>();
    planWarnings.forEach(warning => {
      const artifactId = warning.artifact_id ? String(warning.artifact_id) : '';
      if (!artifactId) return;
      const existing = map.get(artifactId) ?? [];
      existing.push(warning);
      map.set(artifactId, existing);
    });
    return map;
  }, [planWarnings]);
  const blockedCollectionEntries = useMemo(
    () => blockedCollections.map(id => ({ id, name: collectionNameById.get(id) ?? id })),
    [blockedCollections, collectionNameById]
  );
  const commitSummaryByCollectionId = useMemo(() => {
    const map = new Map<string, { confirmation?: string | null; changeset_type?: string | null }>();
    (preview?.per_collection ?? []).forEach(summary => {
      if (!map.has(summary.collection_id)) {
        map.set(summary.collection_id, {
          confirmation: summary.confirmation,
          changeset_type: summary.changeset_type,
        });
      }
    });
    return map;
  }, [preview?.per_collection]);
  const commitProvenance = useMemo(() => {
    const summaries = preview?.per_collection ?? [];
    if (summaries.length === 0) return null;

    const confirmationValues = Array.from(
      new Set(
        summaries
          .map(summary => summary.confirmation)
          .filter((value): value is string => Boolean(value))
      )
    );
    const changesetTypeValues = Array.from(
      new Set(
        summaries
          .map(summary => summary.changeset_type)
          .filter((value): value is string => Boolean(value))
      )
    );

    const confirmationLabel = confirmationValues.length === 0
      ? 'Unknown'
      : confirmationValues.length === 1
        ? formatProvenanceLabel(confirmationValues[0])
        : 'Mixed';
    const changesetTypeLabel = changesetTypeValues.length === 0
      ? 'Unknown'
      : changesetTypeValues.length === 1
        ? formatProvenanceLabel(changesetTypeValues[0])
        : 'Mixed';

    return {
      confirmationLabel,
      changesetTypeLabel,
    };
  }, [preview?.per_collection]);
  const totalArtifacts = preview?.plan.total_artifacts ?? 0;
  const totalAdds = preview?.plan.total_adds ?? 0;
  const totalRemoves = preview?.plan.total_removes ?? 0;
  const selectableArtifactIds = useMemo(
    () => visiblePlanArtifacts.filter(artifact => artifact.action !== 'skipped').map(artifact => artifact.artifact_id),
    [visiblePlanArtifacts]
  );
  const selectedCount = useMemo(() => {
    if (!selectedArtifactIds.length) return 0;
    const allowed = new Set(selectableArtifactIds);
    return selectedArtifactIds.filter(id => allowed.has(id)).length;
  }, [selectedArtifactIds, selectableArtifactIds]);

  const renderArtifactLabel = (change: ArtifactCommitChange) => {
    const artifact = artifactIndex.get(change.artifact_id);
    if (!artifact) return `Artifact ${change.artifact_id}`;

    try {
      if (artifact.context) {
        const ctx = JSON.parse(artifact.context);
        if (ctx.title) return ctx.title as string;
        if (ctx.preview_text) return ctx.preview_text as string;
      }
    } catch (e) {
      console.debug('Failed to parse artifact context for preview label', e);
    }

    if (typeof artifact.content === 'string' && artifact.content.trim().length > 0) {
      return artifact.content.slice(0, 80);
    }

    return `Artifact ${change.artifact_id}`;
  };

  const actionLabel = (action: ArtifactCommitChange['action']) => {
    switch (action) {
      case 'commit':
        return 'Commit';
      case 'skipped':
        return 'Skipped';
      case 'noop':
        return 'No changes';
      default:
        return 'No changes';
    }
  };

  const toggleArtifactExpansion = (artifactId: string) => {
    setExpandedArtifacts(prev => {
      const next = new Set(prev);
      if (next.has(artifactId)) {
        next.delete(artifactId);
      } else {
        next.add(artifactId);
      }
      return next;
    });
  };

  const renderArtifactDiff = (change: ArtifactCommitChange) => {
    const artifact = artifactIndex.get(change.artifact_id);
    if (!artifact) return null;

    try {
      const ctx = artifact.context ? JSON.parse(artifact.context) : {};
      const hasContentChange = change.action === 'commit';
      
      if (!hasContentChange) return null;

      return (
        <div className="mt-2 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs">
          {ctx.title && (
            <div>
              <div className="mb-1 font-medium text-slate-600">Title</div>
              <div className="rounded bg-white p-2 text-slate-900">{ctx.title}</div>
            </div>
          )}
          {ctx.description && (
            <div>
              <div className="mb-1 font-medium text-slate-600">Description</div>
              <div className="rounded bg-white p-2 text-slate-700">{ctx.description}</div>
            </div>
          )}
          {artifact.content && (
            <div>
              <div className="mb-1 font-medium text-slate-600">Content</div>
              <div className="max-h-40 overflow-y-auto rounded bg-white p-2 font-mono text-[10px] text-slate-700 whitespace-pre-wrap">
                {artifact.content.length > 500 ? artifact.content.slice(0, 500) + '\n...(truncated)' : artifact.content}
              </div>
            </div>
          )}
          {change.state_after === 'archived' && (
            <div className="mt-2 flex items-center gap-1 text-xs font-medium text-rose-600">
              <Minus className="h-3 w-3" />
              This artifact will be archived
            </div>
          )}
        </div>
      );
    } catch (e) {
      console.debug('Failed to render artifact diff', e);
      return null;
    }
  };

  const isEmptyState = !isLoading && (!preview || totalArtifacts === 0) && blockedCollections.length === 0;
  const isBlockedOnlyState = !isLoading && totalArtifacts === 0 && blockedCollections.length > 0;
  const publishDisabled = isCommitting || selectedCount === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Publish changes</DialogTitle>
          <DialogDescription className="sr-only">
            Review and select artifacts to publish to collections. Use Tab to navigate, Space to toggle selection, and Enter to publish.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <LoadingState
            title="Preparing preview..."
            description="Identifying adds, removals, and read-only collections."
            density="compact"
          />
        ) : isBlockedOnlyState ? (
          <BlockedState
            title="Collections are read-only"
            description={`${blockedCollections.length} collection${blockedCollections.length === 1 ? '' : 's'} cannot be updated right now.`}
          >
            {blockedCollectionEntries.length > 0 ? (
              <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                {blockedCollectionEntries.map(({ id, name }) => (
                  <li key={id}>{name}</li>
                ))}
              </ul>
            ) : null}
          </BlockedState>
        ) : isEmptyState ? (
          <EmptyState
            title="No pending changes"
            description="Everything is already in sync. Edit cards in the workspace to queue new updates."
            density="compact"
          />
        ) : (
          <div className="space-y-6">
            <div className="grid gap-3 rounded-md border border-slate-200 bg-slate-50 p-4 text-sm">
              <div className="flex flex-wrap items-center gap-4">
                <div>
                  <span className="text-xs uppercase text-slate-500">Cards</span>
                  <div className="text-lg font-semibold text-slate-900">{totalArtifacts}</div>
                </div>
                <Separator orientation="vertical" className="h-10" />
                <div>
                  <span className="text-xs uppercase text-slate-500">Selected</span>
                  <div className="text-lg font-semibold text-slate-900">
                    {selectedCount} / {selectableArtifactIds.length}
                  </div>
                </div>
                <Separator orientation="vertical" className="h-10" />
                <div>
                  <span className="text-xs uppercase text-slate-500">Adds</span>
                  <div className="flex items-center gap-1 font-semibold text-emerald-700">
                    <Plus className="h-4 w-4" />
                    {totalAdds}
                  </div>
                </div>
                <Separator orientation="vertical" className="h-10" />
                <div>
                  <span className="text-xs uppercase text-slate-500">Removes</span>
                  <div className="flex items-center gap-1 font-semibold text-rose-700">
                    <Minus className="h-4 w-4" />
                    {totalRemoves}
                  </div>
                </div>
              </div>
              {blockedCollections.length > 0 && (
                <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  <AlertTriangle className="h-4 w-4" />
                  {blockedCollections.length} collection{blockedCollections.length === 1 ? '' : 's'} will be skipped because they are read-only.
                </div>
              )}
              {planWarnings.length > 0 && (
                <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  <AlertTriangle className="mt-0.5 h-4 w-4" />
                  <div>
                    <div className="font-medium">{planWarnings.length} warning{planWarnings.length === 1 ? '' : 's'} (non-blocking)</div>
                    <div className="text-amber-700">You can still publish, but some decisions/constraints may be missing provenance.</div>
                  </div>
                </div>
              )}
              {commitProvenance && (
                <div className="flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700">
                  <span className="font-medium uppercase tracking-wide text-slate-500">Provenance</span>
                  <span>
                    Confirmation: <span className="font-semibold text-slate-900">{commitProvenance.confirmationLabel}</span>
                  </span>
                  <span>
                    Type: <span className="font-semibold text-slate-900">{commitProvenance.changesetTypeLabel}</span>
                  </span>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onSelectAll}
                  disabled={selectableArtifactIds.length === 0 || selectedCount === selectableArtifactIds.length || isCommitting}
                  aria-label={`Select all ${selectableArtifactIds.length} cards for publishing`}
                >
                  Select all
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onClearSelection}
                  disabled={selectedCount === 0 || isCommitting}
                  aria-label="Clear card selection"
                >
                  Clear selection
                </Button>
              </div>
            </div>

            {planCollections.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Collections</h3>
                <div className="space-y-2 rounded-md border border-slate-200 p-3">
                  {planCollections.map(collection => {
                    const displayName = collectionNameById.get(collection.collection_id) ?? collection.collection_id;
                    const commitSummary = commitSummaryByCollectionId.get(collection.collection_id);
                    const collectionConfirmation = formatProvenanceLabel(commitSummary?.confirmation);
                    const collectionChangesetType = formatProvenanceLabel(commitSummary?.changeset_type);
                    return (
                      <div key={collection.collection_id} className="text-sm">
                        <div className="font-medium text-slate-900">{displayName}</div>
                        <div className="mt-1 text-[11px] text-slate-500" data-testid={`collection-provenance-${collection.collection_id}`}>
                          Collection provenance: <span className="font-medium text-slate-700">{collectionConfirmation}</span> / <span className="font-medium text-slate-700">{collectionChangesetType}</span>
                        </div>
                      <div className="text-xs text-slate-600">
                        {collection.added_artifacts.length > 0 && (
                          <span className="mr-3 text-emerald-700">+{collection.added_artifacts.length} add{collection.added_artifacts.length === 1 ? '' : 's'}</span>
                        )}
                        {collection.removed_artifacts.length > 0 && (
                          <span className="mr-3 text-rose-700">-{collection.removed_artifacts.length} remove{collection.removed_artifacts.length === 1 ? '' : 's'}</span>
                        )}
                        {collection.blocked_adds.length > 0 && (
                          <span className="mr-3 text-amber-700">{collection.blocked_adds.length} blocked add{collection.blocked_adds.length === 1 ? '' : 's'}</span>
                        )}
                        {collection.blocked_removes.length > 0 && (
                          <span className="text-amber-700">{collection.blocked_removes.length} blocked remove{collection.blocked_removes.length === 1 ? '' : 's'}</span>
                        )}
                      </div>
                    </div>
                    );
                  })}
                </div>
              </div>
            )}

            {planWarnings.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Warnings</h3>
                <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  {planWarnings.map((warning, idx) => {
                    const artifactId = warning.artifact_id ? String(warning.artifact_id) : '';
                    const kind = warning.kind ? String(warning.kind) : '';
                    const artifactLabel = artifactId
                      ? renderArtifactLabel({
                          artifact_id: artifactId,
                          action: 'noop',
                          target_collections: [],
                          committed_collections: [],
                          adds: [],
                          removes: [],
                          blocked_adds: [],
                          blocked_removes: [],
                        } as ArtifactCommitChange)
                      : null;

                    return (
                      <div key={`${warning.code}-${artifactId || 'none'}-${idx}`} className="flex items-start gap-2">
                        <AlertTriangle className="mt-0.5 h-4 w-4" />
                        <div>
                          <div className="font-medium">
                            {artifactLabel ? artifactLabel : 'General'}
                            {kind ? <span className="ml-2 text-[10px] uppercase tracking-wide text-amber-700">{kind}</span> : null}
                          </div>
                          <div className="text-amber-800">{warning.message}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {visiblePlanArtifacts.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cards</h3>
                <div className="max-h-72 space-y-2 overflow-y-auto pr-1" role="list" aria-label="Cards to publish">
                  {visiblePlanArtifacts.map(artifact => {
                    const isExpanded = expandedArtifacts.has(artifact.artifact_id);
                    const hasDetails = artifact.action === 'commit';
                    const hasWarnings = (warningsByArtifactId.get(artifact.artifact_id)?.length ?? 0) > 0;
                    
                    return (
                      <div key={artifact.artifact_id} className="rounded-md border border-slate-200 px-3 py-2 text-sm" role="listitem">
                        <div className="flex items-center justify-between gap-3">
                          <label className="flex flex-1 items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              className="h-4 w-4"
                              disabled={artifact.action === 'skipped' || isCommitting}
                              checked={selectedArtifactIds.includes(artifact.artifact_id) && artifact.action !== 'skipped'}
                              onChange={() => onToggleArtifact(artifact.artifact_id)}
                              aria-label={`${selectedArtifactIds.includes(artifact.artifact_id) ? 'Deselect' : 'Select'} ${renderArtifactLabel(artifact)} for publishing`}
                            />
                            <span className="truncate font-medium text-slate-900" title={renderArtifactLabel(artifact)}>
                              {renderArtifactLabel(artifact)}
                            </span>
                          </label>
                          <div className="flex items-center gap-2">
                            {hasWarnings && (
                              <span className="inline-flex items-center gap-1 rounded-md bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800" title="Non-blocking warning for this artifact">
                                <AlertTriangle className="h-3 w-3" />
                                Warning
                              </span>
                            )}
                            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                              {actionLabel(artifact.action)}
                            </span>
                            {hasDetails && (
                              <button
                                onClick={() => toggleArtifactExpansion(artifact.artifact_id)}
                                className="text-slate-400 hover:text-slate-600"
                                aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
                              >
                                {isExpanded ? (
                                  <ChevronDown className="h-4 w-4" />
                                ) : (
                                  <ChevronRight className="h-4 w-4" />
                                )}
                              </button>
                            )}
                          </div>
                        </div>
                        {artifact.skipped_reason && (
                          <div className="mt-1 text-xs text-amber-700">{artifact.skipped_reason}</div>
                        )}
                        {!artifact.skipped_reason && (artifact.adds.length > 0 || artifact.removes.length > 0) && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {artifact.adds.map(collectionId => (
                              <CollectionChip
                                key={collectionId}
                                id={collectionId}
                                name={collectionNameById.get(collectionId)}
                                status="add"
                              />
                            ))}
                            {artifact.removes.map(collectionId => (
                              <CollectionChip
                                key={collectionId}
                                id={collectionId}
                                name={collectionNameById.get(collectionId)}
                                status="remove"
                              />
                            ))}
                          </div>
                        )}
                        {isExpanded && renderArtifactDiff(artifact)}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter className="mt-6">
          <Button 
            variant="ghost" 
            onClick={() => onOpenChange(false)} 
            disabled={isCommitting}
            aria-label="Close publish dialog"
          >
            Close
          </Button>
          <Button 
            variant="outline" 
            onClick={onRefresh} 
            disabled={isLoading || isCommitting}
            aria-label="Refresh commit preview to see latest changes"
          >
            Refresh preview
          </Button>
          <Button 
            onClick={onPublish} 
            disabled={publishDisabled}
            aria-label={isCommitting ? 'Publishing changes' : `Publish ${selectedCount} selected ${selectedCount === 1 ? 'card' : 'cards'} to collections`}
          >
            {isCommitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                Publishing…
              </>
            ) : (
              `Publish ${selectedCount} change${selectedCount === 1 ? '' : 's'}`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
