/**
 * CardContextItems
 *
 * Type-driven context menu content for any artifact. Used inside all artifact shells
 * (CardGridItem, CardListItem, CardTreeItem) and the FloatingCardWindow header.
 *
 * Action resolution priority:
 *   1. contentType.actions[] — explicit actions declared in presentation.json
 *   2. State-based defaults — built-in fallback while types are being enriched
 *
 * Hosts (Browser, WorkspacePanel, …) supply handlers via the `onAction` callback.
 * The action `id` string is passed to `onAction`; hosts map it to the correct
 * async operation (dangerConfirm + service call).
 */
import React from 'react';
import {
  FiTrash2 as TrashIcon,
  FiArrowDownRight as RemoveIcon,
  FiArchive as ArchiveIcon,
  FiRotateCcw as RevertIcon,
  FiRefreshCcw as RestoreIcon,
  FiEye as OpenIcon,
  FiPlus as AddIcon,
  FiFolder as CollectionIcon,
  FiEdit2 as EditIcon,
} from 'react-icons/fi';
import {
  ContextMenuItem,
  ContextMenuSeparator,
} from '../ui/context-menu';
import type { Artifact } from '../../context/workspace/workspace.types';
import type { ContentTypeDefinition } from '@/registry/content-types';
import { isArtifactActionBlocked } from '@/utils/artifact-visual-helpers';

// ─── Public API ───────────────────────────────────────────────────────────────

/** Well-known action IDs understood by all artifact hosts. */
export type CardActionId =
  | 'open'
  | 'edit'
  | 'delete'
  | 'remove'
  | 'archive'
  | 'restore'
  | 'revert'
  | 'add-to-workspace'
  | 'assign-collections';

export interface CardContextItemsProps {
  artifact: Artifact;
  contentType: ContentTypeDefinition;
  /** Called when the user activates a menu item. */
  onAction: (actionId: CardActionId | string, artifact: Artifact) => void;
  /** Whether the artifact is being shown as a search result (affects available actions). */
  isSearchResult?: boolean;
  /** Optional override for the default remove label in host-specific contexts. */
  removeLabel?: string;
}

// ─── Default state-based actions (fallback) ───────────────────────────────────

interface DefaultAction {
  id: CardActionId;
  label: string;
  icon: React.ElementType;
  /** Artifact states where this action is available. Empty = all. */
  states: string[];
  destructive?: boolean;
  separator?: 'before';
}

const DEFAULT_ACTIONS: DefaultAction[] = [
  { id: 'open',    label: 'Open',            icon: OpenIcon,      states: [] },
  { id: 'edit',    label: 'Edit',            icon: EditIcon,      states: ['draft', 'committed'] },
  { id: 'assign-collections', label: 'Assign to collections…', icon: CollectionIcon, states: [] },
  { id: 'revert',  label: 'Revert changes',  icon: RevertIcon,    states: ['draft'], separator: 'before' },
  { id: 'archive', label: 'Archive',         icon: ArchiveIcon,   states: ['committed'] },
  { id: 'restore', label: 'Restore',         icon: RestoreIcon,   states: ['archived'] },
  { id: 'remove',  label: 'Remove from workspace', icon: RemoveIcon, states: ['draft', 'committed'] },
  { id: 'delete',  label: 'Delete',          icon: TrashIcon,     states: ['draft'], destructive: true },
];

const SEARCH_RESULT_ACTIONS: DefaultAction[] = [
  { id: 'open',            label: 'Open',                 icon: OpenIcon,     states: [] },
  { id: 'add-to-workspace', label: 'Add to workspace',   icon: AddIcon,      states: [] },
  { id: 'assign-collections', label: 'Assign to collections…', icon: CollectionIcon, states: [] },
];

// ─── Component ────────────────────────────────────────────────────────────────

export function CardContextItems({
  artifact,
  contentType,
  onAction,
  isSearchResult = false,
  removeLabel,
}: CardContextItemsProps) {
  const state = (artifact.state as string) || 'committed';

  // ── Phase 1: no type-specific actions yet — always use defaults
  // When presentation.json files gain `actions[]`, we'll prefer those here.
  const typeActions = contentType.actions;

  if (typeActions && typeActions.length > 0) {
    // ── Type-driven path ─────────────────────────────────────────────────────
    const applicable = typeActions.filter((a) => {
      if ((!a.states || a.states.length === 0) && !isArtifactActionBlocked(artifact, a.id)) return true;
      return (a.states?.includes(state) ?? false) && !isArtifactActionBlocked(artifact, a.id);
    });

    return (
      <>
        {applicable.map((action) => (
          <ContextMenuItem
            key={action.id}
            onClick={(e) => {
              e.stopPropagation();
              onAction(action.id, artifact);
            }}
            className={action.destructive ? 'text-red-600 focus:text-red-600' : undefined}
          >
            <span className="mr-2 h-4 w-4 inline-flex items-center justify-center opacity-70">
              {/* Icon is a string ID from presentation.json; resolve via icon-map if needed. */}
              {/* For now, omit — hosts can add icons per ID if desired. */}
            </span>
            {action.label}
          </ContextMenuItem>
        ))}
      </>
    );
  }

  // ── State-based fallback ───────────────────────────────────────────────────
  const pool = isSearchResult ? SEARCH_RESULT_ACTIONS : DEFAULT_ACTIONS;

  const applicable = pool.filter((a) => {
    if ((!a.states || a.states.length === 0) && !isArtifactActionBlocked(artifact, a.id)) return true;
    return a.states.includes(state) && !isArtifactActionBlocked(artifact, a.id);
  });

  const items: React.ReactNode[] = [];
  applicable.forEach((action) => {
    if (action.separator === 'before' && items.length > 0) {
      items.push(<ContextMenuSeparator key={`sep-${action.id}`} />);
    }
    const Icon = action.icon;
    items.push(
      <ContextMenuItem
        key={action.id}
        onClick={(e) => {
          e.stopPropagation();
          onAction(action.id, artifact);
        }}
        className={action.destructive ? 'text-red-600 focus:text-red-600' : undefined}
      >
        <Icon className="mr-2 h-4 w-4" />
        {action.id === 'remove' && removeLabel ? removeLabel : action.label}
      </ContextMenuItem>,
    );
  });

  return <>{items}</>;
}

export default CardContextItems;
