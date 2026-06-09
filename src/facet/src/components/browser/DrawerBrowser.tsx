import React from 'react';
import ResourceHeader from '../common/ResourceHeader';
import CardGrid from '../common/CardGrid';
import { Artifact } from '../../context/workspace/workspace.types';
import type { ActiveSource } from '../../types/workspace';
import { X, MoreVertical } from 'lucide-react';

export type DrawerTheme = 'resources' | 'workspace' | 'tools' | 'prompts';

const themeHeaderClass: Record<DrawerTheme, string> = {
  // Resources → Blue
  resources: 'bg-blue-50 text-blue-900',
  // Workspace → Purple
  workspace: 'bg-purple-50 text-purple-900',
  // Tools → Orange
  tools: 'bg-orange-50 text-orange-900',
  // Prompts → Green
  prompts: 'bg-green-50 text-green-900',
};

interface DrawerBrowserProps {
  icon?: React.ReactNode;
  title: string;
  theme: DrawerTheme;
  artifacts: Artifact[];
  activeSource: ActiveSource;
  onClose?: () => void;
}

export default function DrawerBrowser({ icon, title, theme, artifacts, activeSource, onClose }: DrawerBrowserProps) {
  return (
    <div className="flex flex-col h-full">
      <ResourceHeader
        roundedTop
        icon={icon}
        title={title}
        className={themeHeaderClass[theme]}
        inputPlaceholder={theme === 'tools' ? 'Filter tools…' : theme === 'prompts' ? 'Filter prompts…' : 'Filter…'}
        actions={(
          <>
            <button className="h-8 w-8 inline-flex items-center justify-center rounded hover:bg-accent" title="More">
              <MoreVertical className="h-4 w-4" />
            </button>
            {onClose && (
              <button onClick={onClose} className="h-8 w-8 inline-flex items-center justify-center rounded hover:bg-accent" title="Close">
                <X className="h-4 w-4" />
              </button>
            )}
          </>
        )}
      />
      <div className="flex-1 overflow-y-auto bg-white p-4">
        <CardGrid
          artifacts={artifacts}
          selectable={true}
          draggable={false}
          editable={false}
          inPanel={true}
          fillHeight={false}
          activeSource={activeSource}
        />
      </div>
    </div>
  );
}
