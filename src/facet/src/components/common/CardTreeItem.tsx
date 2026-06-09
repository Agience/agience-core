/**
 * CardTreeItem
 *
 * Row component for tree view layout. Phase 1: flat list with indentation
 * support. Recursive nesting is deferred to a later phase.
 */
import { useMemo } from 'react';
import { ChevronRight } from 'lucide-react';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from '../ui/context-menu';
import { Badge } from '../ui/badge';
import { CardContextItems } from './CardContextItems';
import type { CardActionId } from './CardContextItems';
import type { Artifact } from '../../context/workspace/workspace.types';
import { getContentType } from '@/registry/content-types';
import { getArtifactColor, shouldShowStateBadge, getStateBadgeLabel } from '@/utils/artifact-visual-helpers';

interface CardTreeItemProps {
  artifact: Artifact;
  depth?: number;
  isSelected?: boolean;
  isExpanded?: boolean;
  onMouseDown?: (e: React.MouseEvent) => void;
  onToggleExpand?: (artifact: Artifact) => void;
  onOpen?: (artifact: Artifact) => void;
  onRemove?: (artifact: Artifact) => void;
  onRevert?: (artifact: Artifact) => void;
  onArchive?: (artifact: Artifact) => void;
  onRestore?: (artifact: Artifact) => void;
}

function parseTitle(artifact: Artifact): string {
  try {
    const ctx =
      typeof artifact.context === 'string' ? JSON.parse(artifact.context) : artifact.context;
    return ctx?.filename || ctx?.title || 'Untitled';
  } catch {
    return 'Untitled';
  }
}

export function CardTreeItem({
  artifact,
  depth = 0,
  isSelected = false,
  isExpanded = false,
  onMouseDown,
  onToggleExpand,
  onOpen,
  onRemove,
  onRevert,
  onArchive,
  onRestore,
}: CardTreeItemProps) {
  const contentType = useMemo(() => getContentType(artifact), [artifact]);
  const barColor = getArtifactColor(contentType.id);
  const Icon = contentType.icon;
  const title = parseTitle(artifact);
  const indent = depth * 16;

  const handleAction = (actionId: CardActionId | string, actionArtifact: Artifact) => {
    switch (actionId) {
      case 'open':
        onOpen?.(actionArtifact);
        break;
      case 'delete':
      case 'remove':
        onRemove?.(actionArtifact);
        break;
      case 'archive':
        onArchive?.(actionArtifact);
        break;
      case 'restore':
        onRestore?.(actionArtifact);
        break;
      case 'revert':
        onRevert?.(actionArtifact);
        break;
      default:
        break;
    }
  };

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          className={[
            'flex items-center gap-2 h-8 px-2 border-b border-gray-100 cursor-pointer',
            'hover:bg-gray-50 transition-colors',
            isSelected ? 'bg-purple-50 ring-inset ring-1 ring-purple-400' : '',
            artifact.state === 'archived' ? 'opacity-50' : '',
          ].join(' ')}
          style={{ paddingLeft: `${8 + indent}px` }}
          onMouseDown={onMouseDown}
          onDoubleClick={() => onOpen?.(artifact)}
        >
          {/* Expand chevron (only for containers) */}
          {contentType.isContainer ? (
            <button
              type="button"
              className="flex-shrink-0 p-0.5 rounded hover:bg-gray-200 transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                onToggleExpand?.(artifact);
              }}
            >
              <ChevronRight
                size={12}
                className={[
                  'transition-transform text-gray-400',
                  isExpanded ? 'rotate-90' : '',
                ].join(' ')}
              />
            </button>
          ) : (
            <span className="flex-shrink-0 w-4" />
          )}

          {/* Type icon */}
          <Icon size={13} style={{ color: barColor }} className="flex-shrink-0" />

          {/* Title */}
          <span className="flex-1 text-sm text-gray-900 truncate">{title}</span>

          {/* State badge */}
          {shouldShowStateBadge(artifact.state) && (
            <Badge className="bg-gradient-to-br from-purple-400/25 via-pink-400/25 to-blue-400/25 border border-purple-200/50 text-purple-700 text-[10px] px-1.5 py-0 font-medium flex-shrink-0">
              {getStateBadgeLabel(artifact.state)}
            </Badge>
          )}
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <CardContextItems
          artifact={artifact}
          contentType={contentType}
          onAction={handleAction}
        />
      </ContextMenuContent>
    </ContextMenu>
  );
}

export default CardTreeItem;
