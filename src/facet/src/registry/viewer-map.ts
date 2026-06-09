/**
 * viewer-map.ts
 *
 * Maps viewer keys (from presentation.json "viewer" field) to lazy-loaded
 * React component factories.
 *
 * Adding a new content type viewer:
 *   1. Create `src/content-types/<mime>/viewer.tsx` and `index.ts`
 *   2. Import { VIEWER_KEY, factory } from that index here
 *   3. Add [VIEWER_KEY]: factory to VIEWER_MAP
 *
 * vnd.agience.* types use resource_uri / McpAppHost — no compiled viewers here.
 * Standard MIME types (text, image, audio, video, JSON, PDF) are platform-native.
 */
import type { ComponentType } from 'react';
import type { Artifact } from '@/context/workspace/workspace.types';
import type { ViewMode, ViewState } from './content-types';
import {
  VIEWER_KEY as applicationJsonKey,
  factory as applicationJsonFactory,
} from '@/content-types/application/json';
import {
  VIEWER_KEY as applicationPdfKey,
  factory as applicationPdfFactory,
} from '@/content-types/application/pdf';
import {
  VIEWER_KEY as textPlainKey,
  factory as textPlainFactory,
} from '@/content-types/text/plain';
import {
  VIEWER_KEY as textMarkdownKey,
  factory as textMarkdownFactory,
} from '@/content-types/text/markdown';
import {
  VIEWER_KEY as imageKey,
  factory as imageFactory,
} from '@/content-types/image/_wildcard';
import {
  VIEWER_KEY as audioKey,
  factory as audioFactory,
} from '@/content-types/audio/_wildcard';
import {
  VIEWER_KEY as videoKey,
  factory as videoFactory,
} from '@/content-types/video/_wildcard';
import {
  VIEWER_KEY as recordKey,
  factory as recordFactory,
} from '@/content-types/_record';

export type ViewerComponent = ComponentType<{
  artifact: Artifact;
  mode?: ViewMode;
  state?: ViewState;
  /** Optional: navigate to a collection (passed through by container hosts). */
  onOpenCollection?: (collectionId: string) => void;
  onOpenArtifact?: (artifact: Artifact) => void;
}>;

export type ViewerFactory = () => Promise<{ default: ViewerComponent }>;

const defaultFactory: ViewerFactory = () =>
  import('@/content-types/_default/viewer').then((m) => ({ default: m.default as ViewerComponent }));

export { defaultFactory };

export const VIEWER_MAP: Record<string, ViewerFactory> = {
  // Standard MIME type viewers — platform-native, not handler-owned (P12)
  [applicationJsonKey]: applicationJsonFactory as ViewerFactory,
  [applicationPdfKey]: applicationPdfFactory as ViewerFactory,
  [textPlainKey]: textPlainFactory as ViewerFactory,
  [textMarkdownKey]: textMarkdownFactory as ViewerFactory,
  [imageKey]: imageFactory as ViewerFactory,
  [audioKey]: audioFactory as ViewerFactory,
  [videoKey]: videoFactory as ViewerFactory,
  [recordKey]: recordFactory as ViewerFactory,
};

/** Returns the lazy factory for a given viewer key, falling back to the basic artifact viewer. */
export function resolveViewer(key: string | null | undefined): ViewerFactory {
  if (key && VIEWER_MAP[key]) return VIEWER_MAP[key];
  return defaultFactory;
}
