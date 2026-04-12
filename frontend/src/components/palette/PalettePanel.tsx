// src/components/center/PalettePanel.tsx
import React from 'react'
import {
  Play,
  Pause,
  ChevronRight,
  ChevronDown,
  RotateCw,
} from 'lucide-react'

export interface PalettePanelProps {
  label: string
  isExpanded: boolean
  isPaused?: boolean
  forwardState?: 'never' | 'paused' | 'ran' | 'running'
  onExpand: () => void
  onRemove?: () => void
  onPause?: () => void
  onForward?: () => void
  onRedo?: () => void
  onPlay?: () => void
  onClear?: () => void
  onPin?: () => void
  children: React.ReactNode
}

export function PalettePanel({
  label,
  isExpanded,
  isPaused,
  forwardState = 'never',
  onExpand,
  onPause,
  onRedo,
  onPlay,
  children
}: PalettePanelProps) {

  const isRuntimePaused = forwardState === 'paused'

  const iconColorMap: Record<typeof forwardState, string> = {
    never: '',
    running: 'text-blue-600',
    ran: 'text-green-600',
    paused: 'text-red-500',
    
  }

  const actionColor = iconColorMap[forwardState] ?? ''

  return (
    <div className={
      'bg-white ' +
      (isRuntimePaused ? 'ring-2 ring-red-400 ring-inset' : '')
    }>
      {/* Header */}
      <div
        className={
          'flex items-center justify-between p-2 pl-4 ' +
          (isRuntimePaused ? 'bg-red-50' : '')
        }
      >
        {/* Expand icon and label */}
        <div className="flex items-center space-x-1">
          <button
            onClick={e => { e.stopPropagation(); onExpand(); }}
            aria-label={isExpanded ? 'Collapse panel' : 'Expand panel'}
          >
            {isExpanded ? (
              <ChevronDown size={16} />
            ) : (
              <ChevronRight size={16} />
            )}
          </button>
          <span className={
            'font-semibold truncate ' +
            (isRuntimePaused ? 'text-red-700' : '')
          }>{label}</span>
        </div>

        {/* Action buttons */}
        <div className="flex items-center space-x-1">
  {onPause && (
    <button
      onClick={e => { e.stopPropagation(); onPause!(); }}
      title={isPaused ? "Don't pause here" : "Pause here"}
      className="p-1 hover:bg-gray-200 rounded"
    >
      <Pause size={16} className={isPaused ? 'text-red-600' : 'text-gray-400'} />
    </button>
  )}
  {onRedo && (
    <button
      onClick={e => { e.stopPropagation(); onRedo!(); }}
      title="Run this step"
      className="p-1 hover:bg-gray-200 rounded"
    >
      <RotateCw size={16} />
    </button>
  )}
  {onPlay && (
    <button
      onClick={e => { e.stopPropagation(); onPlay!(); }}
      title="Run from here"
      className="p-1 hover:bg-gray-200 rounded"
    >
      <Play size={16} className={actionColor} />
    </button>
  )}
</div>

      </div>

      {/* Body */}
      {isExpanded && (
        <div className="px-4 py-2">
          {children}
        </div>
      )}
    </div>
  )
}
