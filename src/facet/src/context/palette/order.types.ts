import type { PanelData, PanelKey } from './palette.types';

export type TransformSpecVersion = 1;

export type TransformKind =
  | 'palette'
  | 'llm'
  | 'workflow'
  | 'script'
  | 'tool'
  | 'ingest'
  | 'retrieval';

export type TransformRunType =
  | 'palette-run'
  | 'llm'
  | 'mcp-tool'
  | 'flow-run'
  | 'host-script'
  | 'transform-ref'
  | 'order-ref'
  | 'webhook';

export type TransformRunConfig = {
  type: TransformRunType | (string & {});
  server?: string;
  tool?: string;
  input_mapping?: Record<string, unknown>;
  prompt?: string;
  transform_id?: string;
  url?: string;
  host_policy?: string;
  [key: string]: unknown;
};

export type TransformSpecV1 = {
  kind: 'agience.transform' | 'agience.order';
  version: 1;
  title?: string;
  created_time?: string;
  updated_time?: string;

  // Configuration-only: runtime outputs (context/output/panelStatus) are not persisted.
  panelData: Pick<
    PanelData,
    | 'input'
    | 'resources'
    | 'prompts'
    | 'instructions'
    | 'tools'
    | 'knowledge'
    | 'options'
    | 'targets'
  >;

  breakpoints?: PanelKey[];
};

export type TransformSpec = TransformSpecV1;

export type TransformArtifactContext = {
  type?: 'transform' | 'order';
  title?: string;
  content_type?: string;
  transform?: {
    version?: number;
    kind?: TransformKind | (string & {});
    subtype?: string;
    run?: TransformRunConfig;
    spec: TransformSpec;
  };
  order?: {
    version?: number;
    kind?: TransformKind | (string & {});
    subtype?: string;
    run?: TransformRunConfig;
    spec: TransformSpec;
  };
};

export type OrderSpecVersion = TransformSpecVersion;
export type OrderKind = TransformKind;
export type OrderRunType = TransformRunType;
export type OrderRunConfig = TransformRunConfig;
export type OrderSpecV1 = TransformSpecV1;
export type OrderSpec = TransformSpec;
export type OrderArtifactContext = TransformArtifactContext;
