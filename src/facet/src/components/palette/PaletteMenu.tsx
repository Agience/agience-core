// PaletteMenu.tsx
import { createPortal } from 'react-dom';
import { Check } from 'lucide-react';
import { RefObject } from 'react';
import { PanelKey } from '../../context/palette/palette.types';

interface PaletteMenuProps {
  popupRef: RefObject<HTMLDivElement | null>;
  buttonRef: RefObject<HTMLButtonElement | null>;
  panels: ReadonlyArray<{ key: PanelKey; label: string }>;
  visiblePanels: string[];
  showPanel: (key: PanelKey) => void;
  hidePanel: (key: PanelKey) => void;
}

export default function PaletteMenu({
  popupRef,
  buttonRef,
  panels,
  visiblePanels,
  showPanel,
  hidePanel,
}: PaletteMenuProps) {
  const rect = buttonRef.current?.getBoundingClientRect();
  const top = rect ? rect.bottom + window.scrollY : 0;
  const left = rect ? rect.left : 0;

  return createPortal(
    <div ref={popupRef} style={{ position: 'absolute', top, left }}
      className="bg-white border border-gray-200 shadow-lg rounded overflow-hidden min-w-[200px] max-w-[320px]"
    >
      {panels.map(panel => {
        const isVisible = visiblePanels.includes(panel.key);
        return (
          <div
            key={panel.key}
            onClick={() => (isVisible ? hidePanel(panel.key) : showPanel(panel.key))}
            className="flex border-b border-transparent items-center px-4 py-2 space-x-2 cursor-pointer hover:bg-gray-100"
          >
            {<Check size={16} 
                className={`${isVisible ? '' : 'opacity-0'}`} 
            />}
            <span>{panel.label}</span>
          </div>
        );
      })}
    </div>,
    document.body
  );
}
