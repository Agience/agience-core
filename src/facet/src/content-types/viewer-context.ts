/**
 * viewer-context.ts — Platform context interface injected into every content-type viewer.
 *
 * This is the seam between the platform and viewer implementations. Viewers depend on
 * this interface rather than importing React context directly, so the delivery mechanism
 * (bundled, Module Federation, iframe, Web Components) can change without touching handlers.
 *
 * Phase 1: context is passed as a React prop from WorkspaceContext/CollectionContext.
 * Phase N: context is injected at runtime when viewers are loaded remotely.
 */

import type { Artifact } from '../api/types/artifact';
import type { InvokeRequest, InvokeResponse } from '../api/types/invoke';

export type { Artifact, InvokeRequest, InvokeResponse };

/**
 * Context injected into every content-type viewer by the platform.
 * Stable across isolation approaches.
 */
export interface AgienceViewerContext {
  /** The artifact being rendered. */
  artifact: Artifact;

  /** Current workspace ID, or null if viewing a committed collection artifact. */
  workspaceId: string | null;

  /** Platform auth token (Bearer). Attach to any direct API calls. */
  authToken: string;

  /**
   * Mutate the artifact's context or content. Persists to workspace.
   * No-op in read-only collection view.
   */
  updateArtifact: (patch: Partial<Pick<Artifact, 'context' | 'content'>>) => Promise<void>;

  /**
   * Invoke an agent or LLM via POST /agents/invoke.
   * The canonical entry point for all agentic calls from viewer code.
   */
  invoke: (request: InvokeRequest) => Promise<InvokeResponse>;

  /** Open another artifact inline or in a floating window. */
  openArtifact: (artifactId: string, mode?: 'inline' | 'window') => void;
}
