import { useState, useCallback, useRef, useMemo } from 'react';
import {
  PaletteState,
  PaletteProviderProps,
  PanelData,
  PanelKey,
  PanelStatus,
} from './palette.types';

import { PaletteContext } from './PaletteContext';
import type { TransformMeta } from './PaletteContext';
import { useStepHandlers, STEP_KEYS } from './useStepHandler';
import type { TransformSpec } from './order.types';
import { applyTransformSpec } from './orderSpec';

const initialState: PaletteState = {
  panelData: {
    input: { artifacts: [], text: '' },
    resources: { artifacts: [], resources: [] },
    context: { artifacts: [] },
    prompts: { artifacts: [] },
    instructions: { artifacts: [], text: '' },
    tools: { tools: [] },
    knowledge: { artifacts: [] },
    options: { config: {} },
    agent: { config: {} },
    targets: { collections: [] },
    output: { artifacts: [] },
  },
  panelStatus: {} as Record<PanelKey, PanelStatus>,
  updatePanelStatus: () => {},
};

export function PaletteProvider({ children }: PaletteProviderProps) {
  const [state, setState] = useState<PaletteState>(initialState);
  const [nextStep, setNextStep] = useState<PanelKey>(STEP_KEYS[0]);
  const [breakpoints, setBreakpoints] = useState(new Set<PanelKey>());
  const prevPaused = useRef<string | null>(null);

  const [transformMeta, setTransformMeta] = useState<null | TransformMeta>(null);

  const setTransform = useCallback((meta: typeof transformMeta) => {
    setTransformMeta(meta);
    setState((prev) => {
      const nextConfig: Record<string, unknown> = {
        ...((prev.panelData.options?.config as Record<string, unknown>) ?? {}),
      };

      if (meta?.artifactId) nextConfig.order_artifact_id = meta.artifactId;
      else delete nextConfig.order_artifact_id;

      if (meta?.title) nextConfig.order_title = meta.title;
      else delete nextConfig.order_title;

      if (meta?.savedHash) nextConfig.order_saved_hash = meta.savedHash;
      else delete nextConfig.order_saved_hash;

      if (meta?.kind) nextConfig.order_kind = meta.kind;
      else delete nextConfig.order_kind;

      if (meta?.subtype) nextConfig.order_subtype = meta.subtype;
      else delete nextConfig.order_subtype;

      if (meta?.run?.type) nextConfig.order_run_type = meta.run.type;
      else delete nextConfig.order_run_type;

      return {
        ...prev,
        panelData: {
          ...prev.panelData,
          options: {
            ...prev.panelData.options,
            config: nextConfig,
          },
        },
      };
    });
  }, []);

  const [visiblePanels, setVisiblePanels] = useState<PanelKey[]>([
    'resources',
    'tools',
    'prompts',
    'input',
    'targets',
  ]);
  const [maximizedPanels, setMaximizedPanels] = useState<PanelKey[]>([]);

  const [panelStatus, setPanelStatus] = useState<Record<PanelKey, PanelStatus>>(() =>
    Object.fromEntries(STEP_KEYS.map((k) => [k, 'never'])) as Record<PanelKey, PanelStatus>
  );

  const stepHandlers = useStepHandlers();

  const updatePanelStatus = useCallback((key: PanelKey, status: PanelStatus) => {
    setPanelStatus((prev) => ({ ...prev, [key]: status }));
  }, []);

  const updateState = useCallback((updater: (prev: PaletteState) => PaletteState) => {
    setState((prev) => updater(prev));
  }, []);

  // FIX: Use useCallback with empty deps since setState is stable
  const updatePanelData = useCallback(
    function <K extends PanelKey>(
      panelKey: K,
      updater: (prev: PanelData[K]) => PanelData[K]
    ) {
      setState((prevState) => {
        const current = prevState.panelData[panelKey];
        return {
          ...prevState,
          panelData: {
            ...prevState.panelData,
            [panelKey]: updater(current),
          },
        };
      });
    },
    [] // Empty deps - setState is stable, so this callback is stable
  );

  const runFrom = useCallback(
    async (step: PanelKey = STEP_KEYS[0]) => {
      const startIdx = STEP_KEYS.indexOf(step);
      if (startIdx === -1) return;

      let nextState = { ...state };

      for (let i = startIdx; i < STEP_KEYS.length; i++) {
        const key = STEP_KEYS[i];
        const handler = stepHandlers[key];
        if (!handler) continue;

        try {
          updatePanelStatus(key, 'running');
          nextState = await handler(nextState);
          setState(nextState);
          setNextStep(STEP_KEYS[i + 1] ?? key);

          if (breakpoints.has(key)) {
            updatePanelStatus(key, 'paused');
            return;
          }

          updatePanelStatus(key, 'ran');
        } catch (err) {
          console.error(`Error in step handler '${key}':`, err);
          updatePanelStatus(key, 'never');
          break;
        }
      }
    },
    [state, breakpoints, stepHandlers, updatePanelStatus]
  );

  const resume = useCallback(async () => {
    if (nextStep) await runFrom(nextStep);
  }, [nextStep, runFrom]);

  const clear = useCallback(() => {
    setState(initialState);
    setNextStep(STEP_KEYS[0]);
    setBreakpoints(new Set());
    prevPaused.current = null;
    setTransform(null);
  }, [setTransform]);

  const loadTransformSpec = useCallback(
    (spec: TransformSpec, meta?: TransformMeta) => {
      setState((prev) => applyTransformSpec(prev, spec));
      setNextStep(STEP_KEYS[0]);
      setBreakpoints(new Set(spec.breakpoints ?? []));
      prevPaused.current = null;
      setPanelStatus(
        Object.fromEntries(STEP_KEYS.map((k) => [k, 'never'])) as Record<PanelKey, PanelStatus>
      );
      if (meta) setTransform(meta);
    },
    [setTransform]
  );

  const showPanel = useCallback((key: PanelKey) => {
    setVisiblePanels((prev) => (prev.includes(key) ? prev : [...prev, key]));
  }, []);

  const hidePanel = useCallback((key: PanelKey) => {
    setVisiblePanels((prev) => prev.filter((k) => k !== key));
  }, []);

  const maximizePanel = useCallback((key: PanelKey) => {
    setMaximizedPanels((prev) => (prev.includes(key) ? prev : [...prev, key]));
  }, []);

  const minimizePanel = useCallback((key: PanelKey) => {
    setMaximizedPanels((prev) => prev.filter((k) => k !== key));
  }, []);

  const addPause = useCallback((key: PanelKey) => {
    setBreakpoints((prev) => new Set(prev).add(key));
  }, []);

  const removePause = useCallback((key: PanelKey) => {
    setBreakpoints((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
  }, []);

  // Memoize the context value
  const contextValue = useMemo(
    () => ({
      state,
      updateState,
      updatePanelData, // Renamed from updatePanelData
      nextStep,
      breakpoints,
      visiblePanels,
      maximizedPanels,
      panelStatus,
      runFrom,
      resume,
      clear,
      addPause,
      removePause,
      showPanel,
      hidePanel,
      maximizePanel,
      minimizePanel,
      updatePanelStatus,

      transform: transformMeta,
      setTransform,
      loadTransformSpec,
    }),
    [
      state,
      updateState,
      updatePanelData,
      nextStep,
      breakpoints,
      visiblePanels,
      maximizedPanels,
      panelStatus,
      runFrom,
      resume,
      clear,
      addPause,
      removePause,
      showPanel,
      hidePanel,
      maximizePanel,
      minimizePanel,
      updatePanelStatus,
      transformMeta,
      setTransform,
      loadTransformSpec,
      ]
      );

  return (
    <PaletteContext.Provider value={contextValue}>
      {children}
    </PaletteContext.Provider>
  );
}
