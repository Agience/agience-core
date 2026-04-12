// src/components/common/CardListItem.tsx
import { useMemo } from 'react';
import { FiEdit2 as EditIcon } from 'react-icons/fi';
import { ContextMenu, ContextMenuTrigger, ContextMenuContent } from '../ui/context-menu';
import { Badge } from '../ui/badge';
import { Artifact } from '../../context/workspace/workspace.types';
import { DragData } from './CardList';
import { getContentType } from '@/registry/content-types';
import { getArtifactType, getArtifactIcon, getArtifactColor, shouldShowStateBadge, getStateBadgeLabel } from '@/utils/artifact-visual-helpers';
import { CardContextItems } from './CardContextItems';
import type { CardActionId } from './CardContextItems';

interface CardListItemProps {
  artifact: Artifact;
  artifactCount?: number;
  onMouseDown?: (e: React.MouseEvent | React.DragEvent) => void;
  onEdit?: () => void;
  onOpen?: () => void;
  onRemove?: () => void;
  onRevert?: () => void;
  onArchive?: () => void;
  onRestore?: () => void;
  onAddToWorkspace?: () => void;
  onAssignCollections?: () => void;
  draggable?: boolean;
  selectable?: boolean;
  isSelected?: boolean;
  dragData?: DragData;
  editable?: boolean;
  inPanel?: boolean;
  forceHover?: boolean;
  /** Whether the artifact is displayed as a search result (shows Add to workspace instead of Delete). */
  isSearchResult?: boolean;
  removeLabel?: string;
}

// Helper to read upload metadata from artifact.context
function readUpload(artifact: Artifact) {
  try {
    const ctx = typeof artifact.context === 'string' ? JSON.parse(artifact.context) : artifact.context;
    return ctx?.upload as { status?: string; progress?: number; error?: string } | undefined;
  } catch {
    return undefined;
  }
}

// Type for parsed context metadata
type CtxMeta = {
  title?: string;
  filename?: string;
  mime?: string;
  content_type?: string;
  type?: string;
  size?: number;
  tags?: string[];
  collections?: string[];
};

export const CardListItem = ({
  artifact,
  artifactCount = 0,
  onMouseDown,
  onEdit,
  onOpen,
  onRemove,
  onRevert,
  onArchive,
  onRestore,
  onAddToWorkspace,
  onAssignCollections,
  draggable = true,
  selectable = false,
  isSelected = false,
  dragData,
  editable = true,
  forceHover = false,
  isSearchResult = false,
  removeLabel,
}: CardListItemProps) => {
  const { id, state, content } = artifact;

  // Parse context metadata
  const ctx: CtxMeta = useMemo(() => {
    try {
      return typeof artifact.context === 'string' ? JSON.parse(artifact.context) : (artifact.context || {});
    } catch {
      return {};
    }
  }, [artifact.context]);

  // Upload progress
  const upload = readUpload(artifact);
  const isUploading = upload?.status === 'in-progress';
  const uploadProgress = upload?.progress || 0;

  // Display title/filename
  const title = ctx.title || ctx.filename || 'Untitled';

  const artifactType = getArtifactType(artifact);
  const CardIcon = getArtifactIcon(artifactType);
  const artifactBarColor = getArtifactColor(artifactType);

  const contentType = useMemo(() => getContentType(artifact), [artifact]);

  // Timestamp display
  const timestamp = useMemo(() => {
    const date = new Date(artifact.modified_time || artifact.created_time || 0);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) {
      const hours = Math.floor(diff / (1000 * 60 * 60));
      if (hours === 0) {
        const minutes = Math.floor(diff / (1000 * 60));
        return `${minutes}m ago`;
      }
      return `${hours}h ago`;
    }
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  }, [artifact.created_time, artifact.modified_time]);

  // Content preview (first 100 chars)
  const contentPreview = useMemo(() => {
    const text = content || '';
    return text.length > 100 ? text.slice(0, 100) + '...' : text;
  }, [content]);

  // Drag handlers
  const handleDragStart = (e: React.DragEvent) => {
    if (!draggable) {
      e.preventDefault();
      return;
    }
    if (dragData) {
      const ids = Array.isArray(dragData.ids) && dragData.ids.length
        ? dragData.ids
        : [dragData.artifactId];

      const payload = { ...dragData, ids };

      // Primary custom type
      e.dataTransfer.setData('application/x-agience-artifact', JSON.stringify(payload));

      // Fallbacks for environments that strip custom types
      e.dataTransfer.setData('application/json', JSON.stringify(payload));
      e.dataTransfer.setData('text/plain', ids.join(','));

      e.dataTransfer.effectAllowed = 'move';
    }
    onMouseDown?.(e);
  };

  // Double-click to edit
  const handleDoubleClick = () => {
    if (!editable) return;
    if (onOpen) {
      onOpen();
      return;
    }
    onEdit?.();
  };

  // Map CardContextItems action IDs to prop callbacks
  const handleAction = (actionId: CardActionId | string) => {
    switch (actionId) {
      case 'open':
        if (onOpen) { onOpen(); } else { onEdit?.(); }
        break;
      case 'edit':
        onEdit?.();
        break;
      case 'delete':
      case 'remove':
        onRemove?.();
        break;
      case 'archive':
        onArchive?.();
        break;
      case 'restore':
        onRestore?.();
        break;
      case 'revert':
        onRevert?.();
        break;
      case 'add-to-workspace':
        onAddToWorkspace?.();
        break;
      case 'assign-collections':
        onAssignCollections?.();
        break;
      default:
        break;
    }
  };

  return (
    <ContextMenu>
      <ContextMenuTrigger>
        <div
          className={`
            group flex items-center gap-3 px-4 py-3 border-b border-l-4
            hover:bg-gray-50 transition-colors cursor-pointer
            ${state === 'archived' ? 'bg-gray-100 opacity-60 border-b-gray-200' : 'border-b-gray-100'}
            ${isSelected ? 'bg-purple-50 hover:bg-purple-100 ring-2 ring-purple-500' : ''}
            ${forceHover ? 'bg-gray-50' : ''}
            ${isUploading ? 'opacity-60' : ''}
          `}
          style={{ borderLeftColor: artifactBarColor }}
          draggable={draggable}
          onDragStart={handleDragStart}
          onMouseDown={onMouseDown}
          onDoubleClick={handleDoubleClick}
          data-artifact-id={id}
        >
          {/* Selection checkbox (when selectable) */}
          {selectable && (
            <div className="flex items-center">
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => {}} // Handled by parent via onMouseDown
                className="w-4 h-4"
              />
            </div>
          )}

          {/* State badge (only show new, modified, archived) */}
          <div className="flex-shrink-0">
            {shouldShowStateBadge(state) && (
              <Badge className="bg-gradient-to-br from-purple-400/25 via-pink-400/25 to-blue-400/25 border border-purple-200/50 text-purple-700 text-[10px] px-1.5 py-0 font-medium">
                {getStateBadgeLabel(state)}
              </Badge>
            )}
          </div>

          {/* Content area with type icon */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <CardIcon className="flex-shrink-0" size={14} style={{ color: artifactBarColor }} />
              <h3 className="font-medium text-gray-900 truncate">{title}</h3>
              {artifactCount > 0 && (
                <Badge className="border-0 bg-slate-100 text-slate-700 text-[10px] px-1.5 py-0.5 font-medium">
                  {artifactCount} artifact{artifactCount === 1 ? '' : 's'}
                </Badge>
              )}
              {contentType.badgeClassName && (
                <Badge
                  className={`border-0 text-[10px] px-1.5 py-0.5 font-medium ${contentType.badgeClassName}`}
                >
                  {contentType.label}
                </Badge>
              )}
              {ctx.content_type && (
                <span className="text-xs text-gray-400">
                  {ctx.content_type?.split('/')[1]?.toUpperCase()}
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 truncate">{contentPreview}</p>
            
            {/* Tags */}
            {ctx.tags && ctx.tags.length > 0 && (
              <div className="flex gap-1 mt-1 flex-wrap">
                {ctx.tags.slice(0, 3).map((tag) => (
                  <span
                    key={tag}
                    className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded"
                  >
                    {tag}
                  </span>
                ))}
                {ctx.tags.length > 3 && (
                  <span className="text-xs text-gray-400">+{ctx.tags.length - 3}</span>
                )}
              </div>
            )}
          </div>

          {/* Right side: timestamp + file size */}
          <div className="flex-shrink-0 text-right flex items-center gap-2">
            {onEdit && state !== 'archived' && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit();
                }}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-gray-100 text-gray-500 hover:text-gray-700"
                title="Edit"
                aria-label="Edit card"
              >
                <EditIcon className="w-4 h-4" />
              </button>
            )}
            <div>
            <div className="text-xs text-gray-500">{timestamp}</div>
            {ctx.size && (
              <div className="text-xs text-gray-400">
                {(ctx.size / 1024).toFixed(1)} KB
              </div>
            )}
            </div>
          </div>

          {/* Upload progress bar */}
          {isUploading && (
            <div className="absolute bottom-0 left-0 w-full h-1 bg-gray-200">
              <div
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          )}
        </div>
      </ContextMenuTrigger>

      <ContextMenuContent>
        <CardContextItems
          artifact={artifact}
          contentType={contentType}
          onAction={handleAction}
          isSearchResult={isSearchResult}
          removeLabel={removeLabel}
        />
      </ContextMenuContent>
    </ContextMenu>
  );
};
