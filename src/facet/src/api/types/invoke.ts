// api/types/invoke.ts
// Matches POST /artifacts/{id}/invoke — the single entry point for all operator calls.

export interface InvokeRequest {
  /** Transform artifact ID (preferred for product workflows). */
  transform_id?: string;
  /** Named operator. */
  operator?: string;
  /** Workspace scope for context injection. */
  workspace_id?: string;
  /** Artifact IDs injected as context into the operator. */
  artifacts?: string[];
  /** Raw text input. */
  input?: string;
  /** Structured arguments merged with operator_params server-side. */
  params?: Record<string, unknown>;
}

export interface InvokeResponse {
  /** Text output from LLM or task agent. */
  output?: string;
  /** Structured result from task agents. */
  result?: unknown;
  /** Error message if invocation failed. */
  error?: string;
}
