/**
 * api/agent.ts — Canonical operator invocation API.
 *
 * All operator invocations — Transform execution, named operators, and LLM calls —
 * funnel through POST /agents/invoke with a unified request shape:
 *
 *   transform_id  → what Transform artifact to execute
 *   operator      → named operator
 *   workspace_id  → active workspace (scoping + artifact resolution)
 *   artifacts     → artifact IDs to inject as knowledge context
 *   input         → raw text input
 *   params        → structured args for operators / Transform artifacts
 *
 * Identity is always derived server-side from the auth token.
 */

import { post } from './api';
import type { InvokeRequest } from './types';

// ──────────────────────────────────────────────────────────────────────────────
// Demo data
// ──────────────────────────────────────────────────────────────────────────────

// Demo Data Generation Types
interface LoadDemoDataRequest {
  topics?: string[];
  num_workspaces?: number;
  artifacts_per_workspace?: number;
  include_agience_guide?: boolean;
}

interface LoadDemoDataResponse {
  workspaces_created: number;
  workspace_ids: string[];
  workspace_artifacts_created: number;
  agience_guide_added: boolean;
  message: string;
}

/**
 * Generate AI-powered demo data (workspace artifacts and optional Agience Guide)
 */
export async function loadDemoData(request: LoadDemoDataRequest): Promise<LoadDemoDataResponse> {
  const payload = {
    operator: 'demo_data',
    operator_params: {
      topics: request.topics,
      num_workspaces: request.num_workspaces,
      artifacts_per_workspace: request.artifacts_per_workspace,
      include_agience_guide: request.include_agience_guide,
    },
  } as const;

  return post<LoadDemoDataResponse, typeof payload>('/agents/invoke', payload);
}

// ──────────────────────────────────────────────────────────────────────────────
// Information extraction
// ──────────────────────────────────────────────────────────────────────────────

export interface ExtractUnitsResponse {
  workspace_id: string;
  source_artifact_id: string;
  created_artifact_ids: string[];
  unit_count?: number;
  warning?: string;
}

/**
 * Extract structured information units from an artifact.
 *
 * Runs the `extract_units` operator and creates new workspace artifacts for
 * each extracted unit.  Callers should refresh workspace artifacts after this.
 */
export async function extractUnits(
  workspace_id: string,
  source_artifact_id: string,
  artifact_artifact_ids?: string[]
): Promise<ExtractUnitsResponse> {
  const payload: InvokeRequest = {
    operator: 'extract_units:extract_units',
    workspace_id,
    params: {
      source_artifact_id,
      artifact_artifact_ids: artifact_artifact_ids ?? [],
    },
  };
  return post<ExtractUnitsResponse, InvokeRequest>('/agents/invoke', payload);
}

/** Alias for {@link extractUnits} — preferred name for content-type handlers. */
export const extractInformation = extractUnits;
