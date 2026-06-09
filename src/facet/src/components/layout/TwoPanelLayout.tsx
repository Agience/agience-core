/**
 * TwoPanelLayout
 *
 * Pure layout shell with two resizable horizontal panels and a drag handle.
 * Persists panel widths to user preferences under `layout.leftPanelWidth`
 * and `layout.rightPanelWidth`.
 *
 * Replaces ThreeColumnLayout (the sidebar + preview layout is gone; the
 * workspace now occupies the right panel and search occupies the left).
 */
import { ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { usePreferences } from '../../hooks/usePreferences';
import { TooltipProvider } from '@/components/ui/tooltip';
import { LoadingState } from '../common/states';

// ─── Types ────────────────────────────────────────────────────────────────────

interface TwoPanelLayoutProps {
  leftPanel: ReactNode;
  rightPanel: ReactNode;
  /** Callback when panel pixel widths change (useful for header coordination). */
  onPanelWidthsChange?: (widths: { left: number; right: number }) => void;
  /** Callback when resize dragging state changes (useful for coordinating header divider). */
  onResizingChange?: (isResizing: boolean) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function TwoPanelLayout({
  leftPanel,
  rightPanel,
  onPanelWidthsChange,
  onResizingChange,
}: TwoPanelLayoutProps) {
  const { preferences, updatePreferences, isLoading } = usePreferences();
  const containerRef = useRef<HTMLDivElement>(null);

  const savedLayout = useMemo(() => preferences.layout || {}, [preferences.layout]);

  const layoutRecord = savedLayout as Record<string, number>;
  const savedLeftSize = layoutRecord.leftPanelWidth;
  const savedRightSize = layoutRecord.rightPanelWidth;

  // Artifact lane sizing for MVP:
  // - default left panel width ~= two artifacts
  // - minimum left panel width ~= one artifact
  const CARD_WIDTH_PX = 180;
  const CARD_GAP_PX = 12;
  const PANEL_HORIZONTAL_PADDING_PX = 40;
  const ONE_CARD_PANEL_PX = CARD_WIDTH_PX + PANEL_HORIZONTAL_PADDING_PX;
  const TWO_CARD_PANEL_PX = CARD_WIDTH_PX * 2 + CARD_GAP_PX + PANEL_HORIZONTAL_PADDING_PX;
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1366;
  const basisWidth = containerRef.current?.offsetWidth ?? viewportWidth;
  const toPercent = (px: number) => (px / Math.max(1, basisWidth)) * 100;

  const computedMinLeft = Math.max(10, Math.min(55, toPercent(ONE_CARD_PANEL_PX)));
  const computedDefaultLeft = Math.max(computedMinLeft, Math.min(55, toPercent(TWO_CARD_PANEL_PX)));
  const leftSize = savedLeftSize ?? computedDefaultLeft;
  const rightSize = savedRightSize ?? (100 - leftSize);

  const [localLeftSize, setLocalLeftSize] = useState(leftSize);
  const [localRightSize, setLocalRightSize] = useState(rightSize);
  const [isResizing, setIsResizing] = useState(false);

  // Persist with debounce
  const saveTimeoutRef = useRef<number | null>(null);
  const pendingRef = useRef<Partial<Record<string, number>>>({});

  const persistDebounced = useCallback(
    (patch: Record<string, number>, delay = 400) => {
      pendingRef.current = { ...pendingRef.current, ...patch };
      if (saveTimeoutRef.current) window.clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = window.setTimeout(() => {
        updatePreferences({ layout: { ...savedLayout, ...pendingRef.current } });
        pendingRef.current = {};
        saveTimeoutRef.current = null;
      }, delay);
    },
    [savedLayout, updatePreferences],
  );

  // Keep local state in sync when external preferences change
  useEffect(() => {
    setLocalLeftSize(leftSize);
    setLocalRightSize(rightSize);
  }, [leftSize, rightSize]);

  // Notify parent of resize state changes
  useEffect(() => {
    onResizingChange?.(isResizing);
  }, [isResizing, onResizingChange]);

  // Stop resize indicator on pointer release
  useEffect(() => {
    if (!isResizing) return;
    const stop = () => setIsResizing(false);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
    window.addEventListener('mouseup', stop);
    return () => {
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
      window.removeEventListener('mouseup', stop);
    };
  }, [isResizing]);

  // Report pixel widths — useLayoutEffect so header gets correct width before first paint
  // Subtract the 1px handle so the reported width matches the actual panel pixel width.
  const HANDLE_WIDTH_PX = 1;
  useLayoutEffect(() => {
    if (!containerRef.current || !onPanelWidthsChange) return;
    const report = () => {
      if (!containerRef.current || !onPanelWidthsChange) return;
      const available = containerRef.current.offsetWidth - HANDLE_WIDTH_PX;
      onPanelWidthsChange({
        left: (localLeftSize / 100) * available,
        right: (localRightSize / 100) * available,
      });
    };
    report();
    const ro = new ResizeObserver(report);
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [localLeftSize, localRightSize, onPanelWidthsChange]);

  const handleResize = useCallback(
    (sizes: number[]) => {
      if (sizes.length < 2) return;
      const [l, r] = sizes;
      setLocalLeftSize(l);
      setLocalRightSize(r);
      persistDebounced({ leftPanelWidth: l, rightPanelWidth: r }, 500);
      if (containerRef.current && onPanelWidthsChange) {
        const available = containerRef.current.offsetWidth - HANDLE_WIDTH_PX;
        onPanelWidthsChange({ left: (l / 100) * available, right: (r / 100) * available });
      }
    },
    [persistDebounced, onPanelWidthsChange],
  );

  return (
    <TooltipProvider>
      <div ref={containerRef} className="flex h-full w-full overflow-hidden">
        {isLoading ? <LoadingState /> : <PanelGroup id="two-panels" direction="horizontal" onLayout={handleResize}>
          {/* Left panel */}
          <Panel
            id="left-panel"
            order={1}
            defaultSize={localLeftSize}
            minSize={computedMinLeft}
            maxSize={55}
          >
            <div className="h-full overflow-hidden">{leftPanel}</div>
          </Panel>

          {/* Resize handle — 1px border line, no visible gap between panels */}
          <PanelResizeHandle
            id="main-resize"
            onDragging={(dragging) => setIsResizing(dragging)}
            className={`w-px flex-shrink-0 transition-colors cursor-col-resize ${isResizing ? 'bg-purple-500' : 'bg-gray-200 hover:bg-purple-300'}`}
          />

          {/* Right panel */}
          <Panel
            id="right-panel"
            order={2}
            defaultSize={localRightSize}
            minSize={30}
          >
            <div className="h-full overflow-hidden">{rightPanel}</div>
          </Panel>
        </PanelGroup>}
      </div>
    </TooltipProvider>
  );
}

export default TwoPanelLayout;
