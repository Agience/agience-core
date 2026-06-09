/**
 * viewer.tsx — Default (base) viewer for any artifact with no registered viewer
 *
 * When the artifact has displayable content, renders it through ContentRenderer.
 * When content is empty or trivial, shows a friendly summary of available context
 * metadata (description, type, tags) instead of a blank / broken display.
 */
import { useEffect, useMemo, useState } from 'react';
import { ContentRenderer } from '@/components/preview/ContentRenderer';
import type { Artifact } from '@/context/workspace/workspace.types';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { getContentType } from '@/registry/content-types';
import type { ViewMode, ViewState } from '@/registry/content-types';
import { needsContentUrl, resolveArtifactContentUrl } from '@/utils/artifactDownload';
import { getContextContentType, safeParseArtifactContext } from '@/utils/artifactContext';

/** True when content is empty or trivially empty JSON (e.g. "{}" or "[]"). */
function isContentEmpty(content: string | null | undefined): boolean {
  if (!content) return true;
  const trimmed = content.trim();
  return trimmed === '' || trimmed === '{}' || trimmed === '[]' || trimmed === 'null';
}

export default function DefaultViewer({
  artifact,
}: {
  artifact: Artifact;
  mode?: ViewMode;
  state?: ViewState;
  onOpenCollection?: (collectionId: string) => void;
}) {
  const { activeWorkspaceId } = useWorkspaces();
  const parsedContext = useMemo(() => safeParseArtifactContext(artifact.context), [artifact.context]);
  const contentType = useMemo(() => getContentType(artifact), [artifact]);
  const mime = useMemo(
    () => getContextContentType(parsedContext) ?? (typeof parsedContext.content_type === 'string' ? parsedContext.content_type : undefined),
    [parsedContext]
  );
  const filename = useMemo(
    () => (typeof parsedContext.filename === 'string' ? parsedContext.filename : undefined),
    [parsedContext]
  );
  const rawUri = useMemo(
    () => (typeof parsedContext.uri === 'string' ? parsedContext.uri : undefined),
    [parsedContext]
  );
  const [signedUrl, setSignedUrl] = useState<string | undefined>(undefined);

  const shouldFetchUrl = needsContentUrl(mime, parsedContext);

  useEffect(() => {
    if (!shouldFetchUrl) {
      setSignedUrl(undefined);
      return;
    }
    if (rawUri && /^https?:\/\//i.test(rawUri)) {
      setSignedUrl(undefined);
      return;
    }

    let cancelled = false;
    resolveArtifactContentUrl(artifact, activeWorkspaceId ?? undefined)
      .then((url) => {
        if (!cancelled) setSignedUrl(url);
      })
      .catch(() => {
        if (!cancelled) setSignedUrl(undefined);
      });

    return () => {
      cancelled = true;
    };
  }, [activeWorkspaceId, artifact, shouldFetchUrl, rawUri]);

  const displayContent = artifact.content ?? '';

  const description = typeof parsedContext.description === 'string' ? parsedContext.description : undefined;
  const summary = typeof parsedContext.summary === 'string' ? parsedContext.summary : undefined;
  const tags = Array.isArray(parsedContext.tags) ? parsedContext.tags.filter((t): t is string => typeof t === 'string') : [];

  // If we have real content (inline or fetched from S3 via ContentRenderer), render it.
  if (!isContentEmpty(displayContent) || shouldFetchUrl) {
    return (
      <div className="flex flex-col h-full bg-white overflow-y-auto px-4 py-4">
        {parsedContext.title && (
          <h1 className="text-xl font-semibold text-gray-900 mb-4">{parsedContext.title}</h1>
        )}
        <div className="flex-1">
          <ContentRenderer
            content={displayContent}
            mime={mime}
            filename={filename}
            uri={signedUrl ?? rawUri}
          />
        </div>
      </div>
    );
  }

  // Friendly context summary when content is empty
  const Icon = contentType.icon;
  return (
    <div className="flex flex-col h-full bg-white overflow-y-auto px-5 py-5">
      <div className="flex items-start gap-3 mb-4">
        <div
          className="flex items-center justify-center w-10 h-10 rounded-lg shrink-0"
          style={{ backgroundColor: contentType.color + '18' }}
        >
          <Icon className="w-5 h-5" style={{ color: contentType.color }} />
        </div>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-gray-900 leading-tight">
            {parsedContext.title || parsedContext.name || 'Untitled'}
          </h1>
          <span className="text-xs text-gray-400">{contentType.label}</span>
        </div>
      </div>

      {(description || summary) && (
        <p className="text-sm text-gray-600 mb-4 leading-relaxed">
          {description || summary}
        </p>
      )}

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {tags.map((tag) => (
            <span key={tag} className="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600">
              {tag}
            </span>
          ))}
        </div>
      )}

      {!description && !summary && tags.length === 0 && (
        <p className="text-sm text-gray-400 italic">
          No additional details available. Open the context panel to view or edit metadata.
        </p>
      )}
    </div>
  );
}
