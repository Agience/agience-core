import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { Play, RotateCw, Save, SkipBack, SlidersHorizontal } from 'lucide-react';
import { toast } from 'sonner';

import { PanelKey } from '../../context/palette/palette.types';
import { usePalette } from '../../context/palette/PaletteContext';
import type { TransformMeta } from '../../context/palette/PaletteContext';
import { STEP_KEYS } from '../../context/palette/useStepHandler';
import { buildTransformSpec, computeTransformHash, getTransformFromArtifact, makeTransformArtifactContext } from '../../context/palette/orderSpec';
import type { TransformKind, TransformRunConfig, TransformRunType } from '../../context/palette/order.types';
import { getDroppedArtifactIds, isAgienceDrag } from '../../dnd/agienceDrag';
import { useWorkspace } from '../../context/workspace/WorkspaceContext';
import { PaletteProvider } from '../../context/palette/PaletteProvider';
import Palette from './Palette';
import OptionsPanel from './panels/Options';

type TabKey = 'config' | 'inspect';

const CONFIG_PANELS: PanelKey[] = ['resources', 'tools', 'prompts', 'input', 'targets'];
const INSPECT_PANELS: PanelKey[] = ['context', 'instructions', 'knowledge', 'output'];

const TRANSFORM_KIND_OPTIONS: Array<{ value: TransformKind; label: string }> = [
  { value: 'palette', label: 'Palette' },
  { value: 'llm', label: 'LLM' },
  { value: 'workflow', label: 'Workflow' },
  { value: 'script', label: 'Script' },
  { value: 'tool', label: 'Tool' },
  { value: 'ingest', label: 'Ingest' },
  { value: 'retrieval', label: 'Retrieval' },
];

const TRANSFORM_RUN_OPTIONS: Array<{ value: TransformRunType; label: string }> = [
  { value: 'palette-run', label: 'Palette Run' },
  { value: 'llm', label: 'LLM Prompt' },
  { value: 'mcp-tool', label: 'MCP Tool' },
  { value: 'flow-run', label: 'Flow Run' },
  { value: 'host-script', label: 'Host Script' },
  { value: 'transform-ref', label: 'Transform Ref' },
  { value: 'webhook', label: 'Webhook' },
];

function normalizeRunConfig(run?: TransformRunConfig): TransformRunConfig {
  if (!run?.type) return { type: 'palette-run' };
  const normalized = { ...run };
  if (normalized.type === 'order-ref') normalized.type = 'transform-ref';
  if (typeof normalized.transform_id === 'string' && normalized.transform_id.trim() && !normalized.transform_id) {
    normalized.transform_id = normalized.transform_id.trim();
  }
  delete normalized.transform_id;
  return normalized;
}

function updateRunConfig(current: TransformRunConfig | undefined, patch: Partial<TransformRunConfig>): TransformRunConfig {
  const next = { ...normalizeRunConfig(current), ...patch };
  const cleaned: TransformRunConfig = { type: next.type };

  if (typeof next.server === 'string' && next.server.trim()) cleaned.server = next.server.trim();
  if (typeof next.tool === 'string' && next.tool.trim()) cleaned.tool = next.tool.trim();
  if (next.input_mapping && typeof next.input_mapping === 'object' && Object.keys(next.input_mapping).length > 0) cleaned.input_mapping = next.input_mapping;
  if (typeof next.prompt === 'string' && next.prompt.trim()) cleaned.prompt = next.prompt;
  if (typeof next.transform_id === 'string' && next.transform_id.trim()) cleaned.transform_id = next.transform_id.trim();
  if (typeof next.url === 'string' && next.url.trim()) cleaned.url = next.url.trim();
  if (typeof next.host_policy === 'string' && next.host_policy.trim()) cleaned.host_policy = next.host_policy.trim();

  return cleaned;
}

export default function TransformDock(props: { onClose?: () => void }) {
  return (
    <PaletteProvider>
      <TransformDockInner {...props} />
    </PaletteProvider>
  );
}

function TransformDockInner(props: { onClose?: () => void }) {
  const { onClose } = props;
  const {
    state,
    breakpoints,
    visiblePanels,
    showPanel,
    hidePanel,
    clear,
    resume,
    runFrom,
    panelStatus,
    transform,
    setTransform,
    loadTransformSpec,
  } = usePalette();

  const { artifacts, createArtifact, updateArtifact } = useWorkspace();

  const [tab, setTab] = useState<TabKey>('config');
  const [showOptions, setShowOptions] = useState(false);
  const optionsButtonRef = useRef<HTMLButtonElement | null>(null);
  const optionsPopupRef = useRef<HTMLDivElement | null>(null);

  const desiredPanels = useMemo(() => {
    return tab === 'config' ? CONFIG_PANELS : INSPECT_PANELS;
  }, [tab]);

  const allKnownPanels = useMemo(() => {
    return Array.from(new Set([...CONFIG_PANELS, ...INSPECT_PANELS]));
  }, []);

  useEffect(() => {
    // Ensure the correct panels are visible for the active tab.
    const desiredSet = new Set(desiredPanels);
    for (const key of allKnownPanels) {
      const isVisible = visiblePanels.includes(key);
      const shouldBeVisible = desiredSet.has(key);
      if (shouldBeVisible && !isVisible) showPanel(key);
      if (!shouldBeVisible && isVisible) hidePanel(key);
    }
  }, [allKnownPanels, desiredPanels, hidePanel, showPanel, visiblePanels]);

  const pausedStepKey = useMemo(() => {
    return STEP_KEYS.find((k) => panelStatus?.[k] === 'paused') ?? null;
  }, [panelStatus]);

  useEffect(() => {
    if (!pausedStepKey) return;
    if (CONFIG_PANELS.includes(pausedStepKey)) setTab('config');
    else if (INSPECT_PANELS.includes(pausedStepKey)) setTab('inspect');
  }, [pausedStepKey]);

  useEffect(() => {
    function onDocClick(ev: MouseEvent) {
      if (!showOptions) return;
      const t = ev.target as Node;
      if (optionsPopupRef.current?.contains(t)) return;
      if (optionsButtonRef.current?.contains(t)) return;
      setShowOptions(false);
    }
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, [showOptions]);

  const transformTitle = transform?.title ?? 'Unsaved Transform';
  const transformKind = transform?.kind ?? 'palette';
  const transformSubtype = transform?.subtype ?? '';
  const transformRun = normalizeRunConfig(transform?.run);

  const setTransformPatch = useCallback(
    (patch: Partial<TransformMeta>) => {
      setTransform({
        ...(transform ?? {}),
        ...patch,
      });
    },
    [transform, setTransform]
  );

  const saveTransform = useCallback(async () => {
    const now = new Date();
    const spec = buildTransformSpec({
      state,
      breakpoints,
      title: transform?.title ?? `Transform ${now.toLocaleString()}`,
      now,
    });
    const hash = computeTransformHash(spec);
    const title = spec.title ?? 'Transform';
    const ctx = makeTransformArtifactContext({
      title,
      spec,
      kind: transformKind,
      subtype: transformSubtype.trim() || undefined,
      run: transformRun,
    });

    const content = [
      `# ${title}`,
      '',
      'This artifact stores a saved Transform configuration.',
      'Drag this artifact onto the transform dock header to load it.',
      '',
      `transform_hash: ${hash}`,
      `transform_kind: ${transformKind}`,
      `transform_subtype: ${transformSubtype.trim() || '(none)'}`,
      `transform_run_type: ${transformRun.type}`,
      `updated_time: ${spec.updated_time}`,
    ].join('\n');

    try {
      if (transform?.artifactId) {
        await updateArtifact({
          id: transform.artifactId,
          context: JSON.stringify(ctx),
          content,
        });
        setTransform({
          ...transform,
          title,
          savedHash: hash,
          kind: transformKind,
          subtype: transformSubtype.trim() || undefined,
          run: transformRun,
        });
        toast.success('Transform saved');
      } else {
        const created = await createArtifact({
          context: JSON.stringify(ctx),
          content,
        });
        if (created?.id) {
          setTransform({
            artifactId: String(created.id),
            title,
            savedHash: hash,
            kind: transformKind,
            subtype: transformSubtype.trim() || undefined,
            run: transformRun,
          });
          toast.success('Transform saved');
        } else {
          toast.error('Failed to create Transform artifact');
        }
      }
    } catch (err) {
      console.error('Failed to save transform', err);
      toast.error('Failed to save transform');
    }
  }, [breakpoints, createArtifact, transform, transformKind, transformRun, transformSubtype, setTransform, state, updateArtifact]);

  const onHeaderDrop = useCallback(
    (e: DragEvent) => {
      if (!isAgienceDrag(e.dataTransfer)) return;
      e.preventDefault();

      const ids = getDroppedArtifactIds(e.dataTransfer);
      const first = ids[0];
      if (!first) return;
      const artifact = artifacts.find((c) => String(c.id) === String(first));
      if (!artifact) {
        toast.error('Artifact not found in this workspace');
        return;
      }
      const transformFromArtifact = getTransformFromArtifact(artifact);
      if (!transformFromArtifact) {
        toast.error('Dropped artifact is not a Transform');
        return;
      }
      const hash = computeTransformHash(transformFromArtifact.spec);
      loadTransformSpec(transformFromArtifact.spec, {
        artifactId: String(artifact.id ?? ''),
        title: transformFromArtifact.title,
        savedHash: hash,
        kind: transformFromArtifact.kind,
        subtype: transformFromArtifact.subtype,
        run: transformFromArtifact.run,
      });
      toast.success('Transform loaded');
    },
    [artifacts, loadTransformSpec]
  );

  const onHeaderDragOver = useCallback((e: DragEvent) => {
    if (!isAgienceDrag(e.dataTransfer)) return;
    e.preventDefault();
  }, []);

  return (
    <div className="fixed bottom-4 right-4 z-40 pointer-events-auto">
      <div className="w-[520px] max-w-[calc(100vw-2rem)] h-[600px] max-h-[calc(100vh-5rem)] bg-white border border-gray-200 rounded-lg shadow-2xl overflow-hidden resize flex flex-col">
        <div
          className="flex items-center justify-between px-3 py-2 border-b bg-white shrink-0"
          onDrop={onHeaderDrop}
          onDragOver={onHeaderDragOver}
          title="Drop a Transform artifact here to load"
        >
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 mr-2">
              <div className="text-xs px-2 py-1 rounded bg-gray-50 border border-gray-200 text-gray-700 truncate max-w-[180px]">
                {transformTitle}
              </div>
              <button
                onClick={saveTransform}
                title={transform?.artifactId ? 'Save Transform' : 'Save Transform (creates a Transform artifact)'}
                className="p-1 rounded hover:bg-gray-100"
              >
                <Save size={18} />
              </button>
            </div>
            <div className="flex rounded-md border border-gray-200 overflow-hidden">
              <button
                className={
                  'px-3 py-1 text-xs ' +
                  (tab === 'config' ? 'bg-gray-900 text-white' : 'bg-white text-gray-700 hover:bg-gray-50')
                }
                onClick={() => setTab('config')}
              >
                Config
              </button>
              <button
                className={
                  'px-3 py-1 text-xs ' +
                  (tab === 'inspect' ? 'bg-gray-900 text-white' : 'bg-white text-gray-700 hover:bg-gray-50')
                }
                onClick={() => setTab('inspect')}
              >
                Inspect
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              <div className="relative">
                <button
                  ref={optionsButtonRef}
                  onClick={() => setShowOptions((v) => !v)}
                  title="Options"
                  className={
                    'p-1 rounded hover:bg-gray-100 ' +
                    (showOptions ? 'bg-gray-100' : '')
                  }
                >
                  <SlidersHorizontal size={18} />
                </button>
                {showOptions && (
                  <div
                    ref={optionsPopupRef}
                    className="absolute right-0 mt-2 w-[360px] max-w-[calc(100vw-2rem)] bg-white border border-gray-200 rounded-lg shadow-xl p-2 z-50"
                  >
                    <div className="text-xs font-semibold text-gray-700 px-1 pb-1">Options</div>
                    <OptionsPanel />
                  </div>
                )}
              </div>

              <button
                onClick={clear}
                title="Back to start"
                className="p-1 rounded hover:bg-gray-100"
              >
                <SkipBack size={18} />
              </button>
              <button
                onClick={() => pausedStepKey && runFrom(pausedStepKey)}
                title={pausedStepKey ? `Replay ${pausedStepKey}` : 'Replay (paused step)'}
                className="p-1 rounded hover:bg-gray-100 disabled:opacity-40"
                disabled={!pausedStepKey}
              >
                <RotateCw size={18} />
              </button>
              <button
                onClick={resume}
                title="Play"
                className="p-1 rounded hover:bg-gray-100"
              >
                <Play size={18} />
              </button>
            </div>

            {onClose && (
              <button
                className="text-xs text-gray-600 hover:text-gray-900"
                onClick={onClose}
                title="Hide transform dock"
              >
                Hide
              </button>
            )}
          </div>
        </div>

        <div className="grid gap-3 border-b border-gray-200 bg-gray-50 px-3 py-2 md:grid-cols-4">
          <label className="flex flex-col gap-1 text-xs text-gray-600">
            <span className="font-medium text-gray-700">Title</span>
            <input
              value={transform?.title ?? ''}
              onChange={(event) => setTransformPatch({ title: event.target.value })}
              placeholder="Transform title"
              className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-gray-600">
            <span className="font-medium text-gray-700">Kind</span>
            <select
              value={transformKind}
              onChange={(event) => setTransformPatch({ kind: event.target.value as TransformKind })}
              className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
            >
              {TRANSFORM_KIND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs text-gray-600">
            <span className="font-medium text-gray-700">Subtype</span>
            <input
              value={transformSubtype}
              onChange={(event) => setTransformPatch({ subtype: event.target.value || undefined })}
              placeholder="research, summarize, ingest..."
              className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-gray-600">
            <span className="font-medium text-gray-700">Runner</span>
            <select
              value={transformRun.type}
              onChange={(event) => setTransformPatch({ run: updateRunConfig(transformRun, { type: event.target.value as TransformRunType }) })}
              className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
            >
              {TRANSFORM_RUN_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          {transformRun.type === 'mcp-tool' && (
            <>
              <label className="flex flex-col gap-1 text-xs text-gray-600">
                <span className="font-medium text-gray-700">Server</span>
                <input
                  value={transformRun.server ?? 'agience-core'}
                  onChange={(event) => setTransformPatch({ run: updateRunConfig(transformRun, { server: event.target.value }) })}
                  placeholder="agience-core"
                  className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-gray-600 md:col-span-2">
                <span className="font-medium text-gray-700">Tool</span>
                <input
                  value={transformRun.tool ?? ''}
                  onChange={(event) => setTransformPatch({ run: updateRunConfig(transformRun, { tool: event.target.value }) })}
                  placeholder="transcribe"
                  className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
                />
              </label>
            </>
          )}

          {transformRun.type === 'llm' && (
            <label className="flex flex-col gap-1 text-xs text-gray-600 md:col-span-3">
              <span className="font-medium text-gray-700">Prompt</span>
              <input
                value={transformRun.prompt ?? ''}
                onChange={(event) => setTransformPatch({ run: updateRunConfig(transformRun, { prompt: event.target.value }) })}
                placeholder="System prompt template"
                className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
              />
            </label>
          )}

          {transformRun.type === 'transform-ref' && (
            <label className="flex flex-col gap-1 text-xs text-gray-600 md:col-span-2">
              <span className="font-medium text-gray-700">Transform Artifact ID</span>
              <input
                value={transformRun.transform_id ?? ''}
                onChange={(event) => setTransformPatch({ run: updateRunConfig(transformRun, { transform_id: event.target.value }) })}
                placeholder="Target transform artifact id"
                className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
              />
            </label>
          )}

          {transformRun.type === 'webhook' && (
            <label className="flex flex-col gap-1 text-xs text-gray-600 md:col-span-3">
              <span className="font-medium text-gray-700">Webhook URL</span>
              <input
                value={transformRun.url ?? ''}
                onChange={(event) => setTransformPatch({ run: updateRunConfig(transformRun, { url: event.target.value }) })}
                placeholder="https://example.com/hook"
                className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
              />
            </label>
          )}

          {transformRun.type === 'host-script' && (
            <label className="flex flex-col gap-1 text-xs text-gray-600 md:col-span-2">
              <span className="font-medium text-gray-700">Host Policy</span>
              <input
                value={transformRun.host_policy ?? ''}
                onChange={(event) => setTransformPatch({ run: updateRunConfig(transformRun, { host_policy: event.target.value }) })}
                placeholder="signed-only"
                className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-slate-400"
              />
            </label>
          )}
        </div>

        <div className="flex-1 overflow-auto">
          <Palette />
        </div>
      </div>
    </div>
  );
}
