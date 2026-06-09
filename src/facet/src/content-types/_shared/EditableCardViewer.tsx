import { CardEditor } from '@/components/preview/CardEditor';
import RenderedCardViewer from '@/content-types/_shared/RenderedCardViewer';
import type { Artifact } from '@/context/workspace/workspace.types';
import type { ViewMode, ViewState } from '@/registry/content-types';

export default function EditableCardViewer({
  artifact,
  state = 'view',
}: {
  artifact: Artifact;
  mode?: ViewMode;
  state?: ViewState;
  onOpenCollection?: (collectionId: string) => void;
}) {
  if (state !== 'edit') {
    return <RenderedCardViewer artifact={artifact} />;
  }

  if (!artifact.id) {
    return (
      <div className="flex items-center justify-center h-full px-4 text-sm text-gray-400">
        Artifact is not available for editing.
      </div>
    );
  }

  return <CardEditor artifactId={String(artifact.id)} />;
}