/**
 * useArtifactContent — resolves an artifact's text content.
 *
 * When content is stored in S3 (artifact.content is empty but
 * context.content_key is present), fetches it via the download-url API and
 * returns the text once loaded. Falls back to the inline content field for
 * legacy or platform-seeded artifacts that still use it.
 *
 * Returns { content, loading } where `content` is the resolved text string.
 */
import { useEffect, useState } from 'react';
import { safeParseArtifactContext } from '@/utils/artifactContext';
import { resolveArtifactContentUrl } from '@/utils/artifactDownload';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import type { Artifact } from '@/context/workspace/workspace.types';

export function useArtifactContent(artifact: Artifact): { content: string; loading: boolean } {
  const { activeWorkspaceId } = useWorkspaces();
  const [fetched, setFetched] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const inlineContent = artifact.content ?? '';

  // When inline content is present there is nothing to fetch.
  const needsFetch = !inlineContent && Boolean(
    (() => {
      try {
        const ctx = safeParseArtifactContext(artifact.context);
        return ctx.content_key;
      } catch {
        return false;
      }
    })()
  );

  useEffect(() => {
    if (!needsFetch) {
      setFetched(null);
      return;
    }

    let cancelled = false;
    setLoading(true);

    resolveArtifactContentUrl(artifact, activeWorkspaceId ?? undefined)
      .then(async (url) => {
        if (cancelled || !url) return;
        const response = await fetch(url);
        const text = await response.text();
        if (!cancelled) {
          setFetched(text);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFetched(null);
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  // Depend on artifact.id and inlineContent so we re-fetch if the artifact changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifact.id, artifact.context, inlineContent, needsFetch, activeWorkspaceId]);

  return { content: fetched ?? inlineContent, loading };
}
