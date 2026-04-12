import { useEffect, useMemo, useState } from 'react';
import { ContentRenderer } from '@/components/preview/ContentRenderer';
import type { Artifact } from '@/context/workspace/workspace.types';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { needsContentUrl, resolveArtifactContentUrl } from '@/utils/artifactDownload';
import { getContextContentType, safeParseArtifactContext } from '@/utils/artifactContext';

function MetaRow({ label, value }: { label: string; value?: string | number | null }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <div>
      <span className="font-medium text-gray-700">{label}: </span>
      <span>{String(value)}</span>
    </div>
  );
}

export default function RenderedCardViewer({
  artifact,
}: {
  artifact: Artifact;
  mode?: string;
  state?: string;
  onOpenCollection?: (collectionId: string) => void;
}) {
  const { activeWorkspaceId } = useWorkspaces();
  const parsedContext = useMemo(() => safeParseArtifactContext(artifact.context), [artifact.context]);
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
  const bytes = useMemo(() => {
    if (typeof parsedContext.bytes === 'number') return parsedContext.bytes;
    if (typeof parsedContext.size === 'number') return parsedContext.size;
    return undefined;
  }, [parsedContext]);
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

  return (
    <div className="flex flex-col h-full bg-white overflow-y-auto px-4 py-4 gap-4">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
        <MetaRow label="Type" value={mime} />
        <MetaRow label="Filename" value={filename} />
        <MetaRow label="Bytes" value={bytes} />
      </div>
      <div className="min-h-[8rem]">
        <ContentRenderer
          content={artifact.content || ''}
          mime={mime}
          filename={filename}
          uri={signedUrl ?? rawUri}
        />
      </div>
    </div>
  );
}