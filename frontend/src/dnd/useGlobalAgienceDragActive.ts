import { useEffect, useRef, useState } from 'react';
import { AGIENCE_DRAG_CONTENT_TYPE } from './agienceDrag';

function isInternalAgienceDrag(dt: DataTransfer | null | undefined): boolean {
  if (!dt?.types) return false;
  const types = Array.from(dt.types);
  return types.includes(AGIENCE_DRAG_CONTENT_TYPE);
}

/**
 * Tracks whether an internal Agience drag is active anywhere in the document.
 * Used to "pull out" hidden drop rails while dragging.
 */
export function useGlobalAgienceDragActive(): boolean {
  const [active, setActive] = useState(false);
  const depthRef = useRef(0);

  useEffect(() => {
    const onDragEnter = (e: DragEvent) => {
      if (!isInternalAgienceDrag(e.dataTransfer)) return;
      depthRef.current += 1;
      setActive(true);
    };

    const onDragLeave = (e: DragEvent) => {
      if (!isInternalAgienceDrag(e.dataTransfer)) return;
      depthRef.current = Math.max(0, depthRef.current - 1);
      if (depthRef.current === 0) setActive(false);
    };

    const onDrop = () => {
      depthRef.current = 0;
      setActive(false);
    };

    const onDragEnd = () => {
      depthRef.current = 0;
      setActive(false);
    };

    document.addEventListener('dragenter', onDragEnter);
    document.addEventListener('dragleave', onDragLeave);
    document.addEventListener('drop', onDrop);
    document.addEventListener('dragend', onDragEnd);

    return () => {
      document.removeEventListener('dragenter', onDragEnter);
      document.removeEventListener('dragleave', onDragLeave);
      document.removeEventListener('drop', onDrop);
      document.removeEventListener('dragend', onDragEnd);
    };
  }, []);

  return active;
}
