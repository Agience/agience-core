// src/components/center/PaletteContent.tsx
import { PanelKey } from '../../context/palette/palette.types';
import { usePalette } from '../../context/palette/PaletteContext';
import { PALETTE_PANELS } from './PalettePanels';
import { PalettePanel } from './PalettePanel';

export default function Palette() {
  
const {
  visiblePanels,
  breakpoints,
  runFrom,
  addPause,
  removePause,
  maximizedPanels,
  maximizePanel,
  minimizePanel,
  panelStatus,
} = usePalette();

  const isExpanded = (key: PanelKey) => maximizedPanels.includes(key);
  const toggleExpand = (key: PanelKey) =>
    isExpanded(key) ? minimizePanel(key) : maximizePanel(key);

  return (
    <div className="shadow-lg overflow-visible rounded-b-lg">
      {visiblePanels.length > 0 && (
        <div className="divide-y divide-gray-200 rounded-b-lg overflow-hidden">
          {PALETTE_PANELS.filter(p => visiblePanels.includes(p.key)).map(
            ({ key, label, controls, content }) => {
              const paused = breakpoints.has(key);
              const has = (c: 'pause' | 'redo' | 'play') => (controls as unknown as string[]).includes(c);
              const runtimePaused = panelStatus[key] === 'paused';
              const expanded = isExpanded(key) || runtimePaused;

              return (
                // PaletteContent.tsx
                <PalettePanel
                  key={key}
                  label={label}
                  isExpanded={expanded}
                  isPaused={paused}
                  forwardState={panelStatus[key] || 'never'}  // << ADD THIS LINE
                  onExpand={() => toggleExpand(key)}
                  onPause={has('pause') ? () => (paused ? removePause(key) : addPause(key)) : undefined}
                  onRedo={has('redo') ? () => runFrom(key) : undefined}
                  onPlay={has('play') ? () => runFrom(key) : undefined}
                >
                  <div className="p-2">{content}</div>
                </PalettePanel>

              );
            }
          )}
        </div>
      )}
    </div>
  );
}
