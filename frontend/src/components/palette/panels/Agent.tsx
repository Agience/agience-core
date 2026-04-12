import clsx from 'clsx';
import { Octagon, ChevronsRight } from 'lucide-react';
import { usePalette } from '../../../hooks/usePalette';

export default function Agent() {
  const {
    runFrom,
    breakpoints,
    panelStatus,
    addPause,
    removePause,
  } = usePalette();

  const stepKey = 'agent';
  const isPaused = breakpoints.has(stepKey);
  const status = panelStatus[stepKey] ?? 'never';

  const forwardState: 'ready' | 'paused' | 'running' =
    status === 'running' ? 'running' : isPaused ? 'paused' : 'ready';

  const forwardColor: Record<typeof forwardState, string> = {
    ready: 'border border-gray-300 text-gray-500',
    paused: 'bg-red-100 text-red-600',
    running: 'bg-blue-100 text-blue-600',
  };

  const toggleBreakpoint = () => {
    if (isPaused) removePause(stepKey);
    else addPause(stepKey);
  };

  return (
    <div className="w-full">
      <div className="flex w-full py-8">
        <div className="w-1/2 flex justify-center">
          <button
            onClick={toggleBreakpoint}
            title="Toggle breakpoint"
            className="p-2"
          >
            <Octagon
              size={24}
              className={clsx(
                isPaused ? 'text-red-500' : 'text-gray-400',
                'transition-colors'
              )}
            />
          </button>
        </div>

        <div className="w-1/2 flex justify-center">
          <button
            onClick={() => runFrom('agent')}
            title="Run via Agent"
            disabled={status === 'running'}
            className={clsx(
              'p-2 rounded-full focus:outline-none transition-all',
              forwardColor[forwardState]
            )}
          >
            <ChevronsRight size={24} />
          </button>
        </div>
      </div>
    </div>
  );
}
