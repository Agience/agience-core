import React from 'react';
import { cn } from '@/lib/utils';

export interface ResourceHeaderProps {
  icon?: React.ReactNode;
  title: string;
  className?: string;
  rightStatus?: React.ReactNode; // feedback/messages area
  inputPlaceholder?: string;
  inputValue?: string;
  onInputChange?: (value: string) => void;
  actions?: React.ReactNode; // right-side actions (buttons, multi-button)
  roundedTop?: boolean; // when used in a drawer
}

export function ResourceHeader({
  icon,
  title,
  className,
  rightStatus,
  inputPlaceholder = 'Type to filter…',
  inputValue,
  onInputChange,
  actions,
  roundedTop = false,
}: ResourceHeaderProps) {
  return (
    <div className={cn('bg-white border-b border-border', className)}>
      {/* Row 1: left icon + TITLE (xs, uppercase), right status */}
      <div className={cn('flex items-center justify-between px-3 h-8', roundedTop && 'rounded-t')}>
        <div className="flex items-center gap-1.5 min-w-0">
          {icon}
          <div className="text-xs uppercase tracking-wide text-muted-foreground font-semibold truncate">
            {title}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {rightStatus}
        </div>
      </div>
      {/* Row 2: input + actions */}
      <div className="flex items-center gap-2 px-3 py-1">
        <input
          className="flex-1 h-8 px-2 text-sm border rounded outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40 bg-white"
          placeholder={inputPlaceholder}
          value={inputValue}
          onChange={(e) => onInputChange?.(e.target.value)}
        />
        <div className="flex items-center gap-2">
          {actions}
        </div>
      </div>
    </div>
  );
}

export default ResourceHeader;
