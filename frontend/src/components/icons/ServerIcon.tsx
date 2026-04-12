// ServerIcon.tsx
// Dynamic server icon component that renders based on server's icon metadata

import React from 'react';
import McpIcon from './McpIcon';
import { AgienceResourcesIcon, AgienceToolsIcon, AgiencePromptsIcon } from './AgienceIcons';
import { Wrench, FolderOpen, LayoutTemplate } from 'lucide-react';

interface ServerIconProps {
  icon?: string;
  type?: 'resources' | 'tool' | 'prompt';
  size?: number;
  className?: string;
}

/**
 * Renders a server-specific icon based on icon metadata from MCP initialization.
 * 
 * Icon formats supported:
 * - "agience": Uses Agience-branded icons (differentiated by type)
 * - URL (http:// or https://): Renders as <img>
 * - Data URI (data:image/...): Renders as <img>
 * - Emoji (single character): Renders as text
 * - undefined/null: Falls back to generic MCP icon
 * 
 * @param icon - Icon string from serverInfo._meta.icon or "agience" marker
 * @param type - Resource type for Agience-branded icon selection
 * @param size - Icon size in pixels
 * @param className - Additional CSS classes
 */
export const ServerIcon: React.FC<ServerIconProps> = ({ 
  icon, 
  type = 'resources',
  size = 16, 
  className = '' 
}) => {
  // Agience-branded icons
  if (icon === 'agience') {
    switch (type) {
      case 'resources':
        return <AgienceResourcesIcon size={size} className={className} />;
      case 'tool':
        return <AgienceToolsIcon size={size} className={className} />;
      case 'prompt':
        return <AgiencePromptsIcon size={size} className={className} />;
      default:
        return <AgienceResourcesIcon size={size} className={className} />;
    }
  }
  
  // URL-based icon (http:// or https://)
  if (icon && (icon.startsWith('http://') || icon.startsWith('https://'))) {
    return (
      <img 
        src={icon} 
        alt="Server icon"
        width={size}
        height={size}
        className={className}
        style={{ objectFit: 'contain' }}
      />
    );
  }
  
  // Data URI (data:image/...)
  if (icon && icon.startsWith('data:image/')) {
    return (
      <img 
        src={icon} 
        alt="Server icon"
        width={size}
        height={size}
        className={className}
        style={{ objectFit: 'contain' }}
      />
    );
  }
  
  // Emoji (single character or short string)
  if (icon && icon.length <= 4) {
    return (
      <span 
        className={className}
        style={{ 
          fontSize: `${size}px`, 
          lineHeight: 1,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        {icon}
      </span>
    );
  }
  
  // Fallback to type-specific generic icons
  switch (type) {
    case 'resources':
      return <FolderOpen size={size} className={className} />;
    case 'tool':
      return <Wrench size={size} className={className} />;
    case 'prompt':
      return <LayoutTemplate size={size} className={className} />;
    default:
      return <McpIcon size={size} className={className} />;
  }
};

export default ServerIcon;
