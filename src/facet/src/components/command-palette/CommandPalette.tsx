/**
 * CommandPalette - Global search and navigation interface
 * 
 * Gmail-style command palette triggered by Cmd+K (Mac) or Ctrl+K (Windows/Linux).
 * Provides fuzzy search across workspaces, collections, and MCP servers with
 * recent items tracking.
 * 
 * Features:
 * - Keyboard shortcut (⌘K / Ctrl+K)
 * - Fuzzy search with cmdk
 * - Recent items (localStorage, max 5)
 * - Keyboard navigation (↑↓ arrows, Enter)
 * - 5 groups: Recent, Workspaces, Collections, MCP Servers, Quick Actions
 * 
 * @example
 * ```tsx
 * <CommandPalette
 *   onWorkspaceSelect={(id) => setActiveWorkspace(id)}
 *   onCollectionSelect={(id) => openCollection(id)}
 *   onMcpServerSelect={(id) => openMcpServer(id)}
 * />
 * ```
 */

import { useEffect, useState, useCallback } from 'react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import { NotebookPen, FolderOpen, Search, Wand2 } from 'lucide-react';
import McpIcon from '../icons/McpIcon';
import { useWorkspaces } from '../../hooks/useWorkspaces';
import { useWorkspace } from '../../hooks/useWorkspace';
import { CollectionResponse } from '../../api/types';
import { listCollections } from '../../api/collections';
import { useShortcuts } from '@/context/shortcuts/useShortcuts';

interface CommandPaletteProps {
  /** Callback when a workspace is selected */
  onWorkspaceSelect?: (workspaceId: string) => void;
  /** Callback when a collection is selected */
  onCollectionSelect?: (collectionId: string) => void;
  /** Callback when an MCP server is selected */
  onMcpServerSelect?: (serverId: string) => void;
}

interface RecentItem {
  type: 'workspace' | 'collection' | 'mcp-server';
  id: string;
  name: string;
  timestamp: number;
}

const RECENT_ITEMS_KEY = 'agience-recent-items';
const MAX_RECENT_ITEMS = 5;

export default function CommandPalette({
  onWorkspaceSelect,
  onCollectionSelect,
  onMcpServerSelect,
}: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [collections, setCollections] = useState<CollectionResponse[]>([]);
  const [recentItems, setRecentItems] = useState<RecentItem[]>([]);
  const { workspaces, setActiveWorkspaceId } = useWorkspaces();
  const { selectedArtifactIds, extractInformationFromSelection } = useWorkspace();
  const { registerShortcut } = useShortcuts();

  // Mock MCP servers - TODO: Replace with actual API call
  const mcpServers = [
    { id: 'agience_core', name: 'Agience' }
  ];

  // Load collections
  useEffect(() => {
    listCollections()
      .then(setCollections)
      .catch(console.error);
  }, []);

  // Load recent items from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem(RECENT_ITEMS_KEY);
      if (stored) {
        setRecentItems(JSON.parse(stored));
      }
    } catch (error) {
      console.error('Failed to load recent items:', error);
    }
  }, []);

  // Save recent item
  const addRecentItem = useCallback((type: RecentItem['type'], id: string, name: string) => {
    setRecentItems((prev) => {
      // Remove if already exists
      const filtered = prev.filter(item => !(item.type === type && item.id === id));
      // Add to front
      const updated = [{ type, id, name, timestamp: Date.now() }, ...filtered].slice(0, MAX_RECENT_ITEMS);
      // Save to localStorage
      try {
        localStorage.setItem(RECENT_ITEMS_KEY, JSON.stringify(updated));
      } catch (error) {
        console.error('Failed to save recent items:', error);
      }
      return updated;
    });
  }, []);

  useEffect(() => {
    return registerShortcut({
      id: 'shortcuts:command-palette',
      label: 'Open command palette',
      group: 'Navigation',
      groupTitle: 'Navigation',
      groupOrder: 1,
      combos: ['mod+k'],
      handler: (event) => {
        event.preventDefault();
        setOpen((current) => !current);
      },
      options: {
        description: 'Search workspaces, collections, and quick actions',
        allowInInputs: true,
        order: 5,
      },
    });
  }, [registerShortcut]);

  // Handle workspace selection
  const handleWorkspaceSelect = useCallback((workspaceId: string, workspaceName: string) => {
    addRecentItem('workspace', workspaceId, workspaceName);
    setActiveWorkspaceId(workspaceId);
    onWorkspaceSelect?.(workspaceId);
    setOpen(false);
  }, [setActiveWorkspaceId, onWorkspaceSelect, addRecentItem]);

  // Handle collection selection
  const handleCollectionSelect = useCallback((collectionId: string, collectionName: string) => {
    addRecentItem('collection', collectionId, collectionName);
    onCollectionSelect?.(collectionId);
    setOpen(false);
  }, [onCollectionSelect, addRecentItem]);

  // Handle MCP server selection
  const handleMcpServerSelect = useCallback((serverId: string, serverName: string) => {
    addRecentItem('mcp-server', serverId, serverName);
    onMcpServerSelect?.(serverId);
    setOpen(false);
  }, [onMcpServerSelect, addRecentItem]);

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search workspaces, collections, MCP servers..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        {/* Recent Items Group */}
        {recentItems.length > 0 && (
          <>
            <CommandGroup heading="Recent">
              {recentItems.map((item) => {
                const Icon = item.type === 'workspace' 
                  ? NotebookPen 
                  : item.type === 'collection' 
                  ? FolderOpen 
                  : McpIcon;
                
                return (
                  <CommandItem
                    key={`recent-${item.type}-${item.id}`}
                    value={`recent-${item.type}-${item.name}`}
                    onSelect={() => {
                      if (item.type === 'workspace') handleWorkspaceSelect(item.id, item.name);
                      else if (item.type === 'collection') handleCollectionSelect(item.id, item.name);
                      else handleMcpServerSelect(item.id, item.name);
                    }}
                    className="cursor-pointer"
                  >
                    {item.type === 'mcp-server' ? (
                      <McpIcon size={16} className="mr-2 text-gray-500" />
                    ) : (
                      <Icon className="mr-2 h-4 w-4 text-gray-500" />
                    )}
                    <span className="font-medium text-sm truncate">{item.name}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        {/* Workspaces Group */}
        {workspaces.length > 0 && (
          <>
            <CommandGroup heading="Workspaces">
              {workspaces.map((workspace) => (
                <CommandItem
                  key={workspace.id}
                  value={`workspace-${workspace.name}`}
                  onSelect={() => handleWorkspaceSelect(workspace.id, workspace.name)}
                  className="cursor-pointer"
                >
                  <NotebookPen className="mr-2 h-4 w-4 text-gray-500" />
                  <div className="flex flex-col flex-1 min-w-0">
                    <span className="font-medium text-sm truncate">{workspace.name}</span>
                    {workspace.description && (
                      <span className="text-xs text-gray-500 truncate">
                        {workspace.description}
                      </span>
                    )}
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        {/* Collections Group */}
        {collections.length > 0 && (
          <>
            <CommandGroup heading="Collections">
              {collections.map((collection) => (
                <CommandItem
                  key={collection.id}
                  value={`collection-${collection.name}`}
                  onSelect={() => handleCollectionSelect(collection.id, collection.name)}
                  className="cursor-pointer"
                >
                  <FolderOpen className="mr-2 h-4 w-4 text-gray-500" />
                  <div className="flex flex-col flex-1 min-w-0">
                    <span className="font-medium text-sm truncate">{collection.name}</span>
                    {collection.description && (
                      <span className="text-xs text-gray-500 truncate">
                        {collection.description}
                      </span>
                    )}
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        {/* MCP Servers Group */}
        {mcpServers.length > 0 && (
          <CommandGroup heading="MCP Servers">
            {mcpServers.map((server) => (
              <CommandItem
                key={server.id}
                value={`mcp-${server.name}`}
                onSelect={() => handleMcpServerSelect(server.id, server.name)}
                className="cursor-pointer"
              >
                <McpIcon size={16} className="mr-2 text-gray-500" />
                <span className="font-medium text-sm">{server.name}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {/* Quick Actions Group */}
        <CommandSeparator />
        <CommandGroup heading="Quick Actions">
          <CommandItem
            value="extract-units"
            onSelect={() => {
              setOpen(false);
              void extractInformationFromSelection();
            }}
            className="cursor-pointer"
          >
            <Wand2 className="mr-2 h-4 w-4 text-gray-500" />
            <span className="text-sm">
              Extract information{selectedArtifactIds.length > 0 ? ` (${selectedArtifactIds.length} selected)` : ''}
            </span>
          </CommandItem>
          <CommandItem
            value="search-artifacts"
            onSelect={() => {
              // TODO: Implement global artifact search
              setOpen(false);
            }}
            className="cursor-pointer"
          >
            <Search className="mr-2 h-4 w-4 text-gray-500" />
            <span className="text-sm">Search cards...</span>
          </CommandItem>
          <CommandItem
            value="create-workspace"
            onSelect={() => {
              // TODO: Trigger workspace creation modal
              setOpen(false);
            }}
            className="cursor-pointer"
          >
            <NotebookPen className="mr-2 h-4 w-4 text-gray-500" />
            <span className="text-sm">Create Workspace</span>
          </CommandItem>
          <CommandItem
            value="create-collection"
            onSelect={() => {
              // TODO: Trigger collection creation modal
              setOpen(false);
            }}
            className="cursor-pointer"
          >
            <FolderOpen className="mr-2 h-4 w-4 text-gray-500" />
            <span className="text-sm">Create Collection</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
