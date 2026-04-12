import type { Artifact } from '../workspace/workspace.types';
import type { PanelData, PanelKey, PaletteState } from './palette.types';
import type { TransformArtifactContext, TransformKind, TransformRunConfig, TransformSpec, TransformSpecV1 } from './order.types';
import { TRANSFORM_CONTENT_TYPE } from '@/utils/content-type';

function safeJsonParse<T>(raw: unknown): T | null {
  if (typeof raw !== 'string' || !raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function buildTransformSpec(args: {
  state: PaletteState;
  breakpoints: Set<PanelKey>;
  title?: string;
  now?: Date;
}): TransformSpec {
  const { state, breakpoints, title, now } = args;
  const created_time = (now ?? new Date()).toISOString();

  const panelData: TransformSpecV1['panelData'] = {
    input: {
      artifacts: state.panelData.input?.artifacts ?? [],
      text: state.panelData.input?.text ?? '',
    },
    resources: {
      artifacts: state.panelData.resources?.artifacts ?? [],
      resources: state.panelData.resources?.resources ?? [],
    },
    prompts: {
      artifacts: state.panelData.prompts?.artifacts ?? [],
      selectedId: state.panelData.prompts?.selectedId,
    },
    instructions: {
      artifacts: state.panelData.instructions?.artifacts ?? [],
      text: state.panelData.instructions?.text ?? '',
    },
    tools: {
      tools: state.panelData.tools?.tools ?? [],
    },
    knowledge: {
      artifacts: state.panelData.knowledge?.artifacts ?? [],
    },
    options: {
      config: (state.panelData.options?.config ?? {}) as Record<string, unknown>,
    },
    targets: {
      collections: state.panelData.targets?.collections ?? [],
    },
  };

  return {
    kind: 'agience.transform',
    version: 1,
    title,
    created_time,
    updated_time: created_time,
    panelData,
    breakpoints: Array.from(breakpoints),
  };
}

export function applyTransformSpec(prev: PaletteState, spec: TransformSpec): PaletteState {
  const nextPanelData: PanelData = {
    ...prev.panelData,

    input: spec.panelData.input,
    resources: spec.panelData.resources,
    prompts: spec.panelData.prompts,
    instructions: spec.panelData.instructions,
    tools: spec.panelData.tools,
    knowledge: spec.panelData.knowledge,
    options: spec.panelData.options,
    targets: spec.panelData.targets,

    // Derived/output panels are reset for a clean run.
    context: { artifacts: [] },
    output: { artifacts: [] },
  };

  return {
    ...prev,
    panelData: nextPanelData,
  };
}

export function getTransformFromArtifact(artifact: Artifact): {
  title?: string;
  kind?: TransformKind | string;
  subtype?: string;
  run?: TransformRunConfig;
  spec: TransformSpec;
} | null {
  const ctx = safeJsonParse<TransformArtifactContext>(artifact.context);
  const transform = ctx?.transform ?? ctx?.order;
  const spec = transform?.spec;
  if (!spec || typeof spec !== 'object') return null;
  if ((spec as TransformSpec).kind !== 'agience.transform' && (spec as TransformSpec).kind !== 'agience.order') return null;
  if ((spec as TransformSpec).version !== 1) return null;
  return {
    title: ctx?.title ?? spec.title,
    kind: transform?.kind,
    subtype: transform?.subtype,
    run: transform?.run,
    spec: spec as TransformSpec,
  };
}

export function makeTransformArtifactContext(args: {
  title: string;
  spec: TransformSpec;
  kind?: TransformKind | string;
  subtype?: string;
  run?: TransformRunConfig;
}): TransformArtifactContext {
  return {
    type: 'transform',
    title: args.title,
    content_type: TRANSFORM_CONTENT_TYPE,
    transform: {
      version: 1,
      kind: args.kind ?? 'palette',
      ...(args.subtype ? { subtype: args.subtype } : {}),
      ...(args.run ? { run: args.run } : {}),
      spec: args.spec,
    },
  };
}

export function computeTransformHash(spec: TransformSpec): string {
  // Good-enough UI hash: stable-ish JSON via sorted keys.
  const stable = stableStringify(spec);
  return `v1:${simpleHash(stable)}`;
}

export const buildOrderSpec = buildTransformSpec;
export const applyOrderSpec = applyTransformSpec;
export const getOrderFromArtifact = getTransformFromArtifact;
export const makeOrderArtifactContext = makeTransformArtifactContext;
export const computeOrderHash = computeTransformHash;

function stableStringify(value: unknown): string {
  return JSON.stringify(sortKeysDeep(value));
}

function sortKeysDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeysDeep);
  if (!value || typeof value !== 'object') return value;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  const out: Record<string, unknown> = {};
  for (const k of keys) out[k] = sortKeysDeep(obj[k]);
  return out;
}

function simpleHash(input: string): string {
  // Deterministic, not cryptographic.
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).padStart(8, '0');
}
