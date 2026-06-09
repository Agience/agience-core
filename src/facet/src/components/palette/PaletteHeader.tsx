import { ChevronDown, SkipBack, Play, FastForward } from 'lucide-react'; // add FastForward icon
import { useState, useEffect, useRef } from 'react';
import PaletteMenu from './PaletteMenu';
import { PALETTE_PANELS } from './PalettePanels';
import { usePalette } from '../../context/palette/PaletteContext';

export default function PaletteHeader() {
  const {
    clear,
    resume,
    runFrom,           // << Add this
    visiblePanels,
    showPanel,
    hidePanel,
  } = usePalette();

  const [openMenu, setOpenMenu] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const popupRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onClick(ev: MouseEvent) {
      if (
        !popupRef.current?.contains(ev.target as Node) &&
        !menuButtonRef.current?.contains(ev.target as Node)
      ) {
        setOpenMenu(false);
      }
    }
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, []);

  return (
    <div className="flex items-center justify-between p-2 border-b bg-white">
      <div className="relative">
        <button
          ref={menuButtonRef}
          onClick={() => setOpenMenu(p => !p)}
          className="flex items-center space-x-1 pl-2 pr-3 py-1 border border-gray-300 hover:bg-gray-200 rounded"
        >
          <ChevronDown size={16} />
          <span>Panels</span>
        </button>
        {openMenu && (
          <PaletteMenu
            popupRef={popupRef}
            buttonRef={menuButtonRef}
            panels={PALETTE_PANELS}
            visiblePanels={visiblePanels}
            showPanel={showPanel}
            hidePanel={hidePanel}
          />
        )}
      </div>
            
      
      <div className="flex space-x-2 pr-2">
        <button onClick={clear} title="Start Over">
          <SkipBack size={20} />
        </button>
        <button onClick={() => runFrom('input')} title="Run All">
          <FastForward size={20} />
        </button>
        <button onClick={resume} title="Continue">
          <Play size={18} />
        </button>
      </div>
    </div>
  );
}
