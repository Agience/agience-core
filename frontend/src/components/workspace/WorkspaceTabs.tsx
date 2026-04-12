/**
 * WorkspaceTabs
 *
 * Horizontal tab strip for switching between workspaces.
 * Extracted from BrowserHeader; replaces the inline tab logic there.
 */
import { useEffect, useState } from 'react';
import { FiPlus } from 'react-icons/fi';
import { Tabs, TabsList, TabsTrigger } from '../ui/tabs';
import { useWorkspaces } from '../../hooks/useWorkspaces';

// ─── Component ────────────────────────────────────────────────────────────────

export function WorkspaceTabs() {
  const { workspaces, activeWorkspace, setActiveWorkspaceId, createWorkspace } = useWorkspaces();

  const [activeTab, setActiveTab] = useState<string | undefined>(
    activeWorkspace?.id || workspaces[0]?.id,
  );

  // Keep local tab state in sync with context
  useEffect(() => {
    if (activeWorkspace?.id) setActiveTab(activeWorkspace.id);
  }, [activeWorkspace?.id]);

  const handleTabChange = (id: string) => {
    setActiveTab(id);
    setActiveWorkspaceId(id);
  };

  const handleCreate = async () => {
    const name = window.prompt('Workspace name:');
    if (!name) return;
    try {
      const ws = await createWorkspace(name, '');
      setActiveTab(ws.id);
      setActiveWorkspaceId(ws.id);
    } catch {
      window.alert('Failed to create workspace');
    }
  };

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full min-w-0">
      <div className="flex items-center gap-1 overflow-x-auto scrollbar-thin w-full">
        <TabsList className="bg-transparent h-auto p-0 flex-shrink-0 gap-1">
          {workspaces.map((ws) => (
            <TabsTrigger
              key={ws.id}
              value={ws.id}
              className={[
                'h-8 px-4 rounded-sm border text-sm font-medium whitespace-nowrap transition-all',
                'data-[state=active]:bg-gradient-to-r data-[state=active]:from-blue-400/20',
                'data-[state=active]:via-pink-400/20 data-[state=active]:to-purple-400/20',
                'data-[state=active]:border-purple-300/40 data-[state=active]:text-purple-900',
                'data-[state=inactive]:bg-white/50 data-[state=inactive]:border-purple-200/30',
                'data-[state=inactive]:text-gray-700 data-[state=inactive]:hover:bg-purple-50/30',
                'data-[state=inactive]:hover:border-purple-300/40',
              ].join(' ')}
            >
              {ws.name}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* New workspace button */}
        <button
          type="button"
          onClick={handleCreate}
          className="flex-shrink-0 h-8 w-8 inline-flex items-center justify-center rounded-sm border border-purple-200/30 bg-white/50 text-gray-700 hover:bg-purple-50/30 hover:border-purple-300/40 transition-all"
          title="Create new workspace"
        >
          <FiPlus className="w-4 h-4" />
        </button>
      </div>
    </Tabs>
  );
}

export default WorkspaceTabs;
