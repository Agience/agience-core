/**
 * OrderCardViewer
 *
 * Viewer for `application/vnd.agience.transform+json` artifacts.
 * Registered in viewer-map as `'transform'`.
 *
 * PaletteProvider is now mounted by the host via the declarable provider
 * system (presentation.json `"provider": "palette"`).  This component
 * consumes that context directly.
 */
import { useEffect } from 'react';
import type { Artifact } from '../../context/workspace/workspace.types';
import { computeTransformHash, getTransformFromArtifact } from '../../context/palette/orderSpec';
import { usePalette } from '../../context/palette/PaletteContext';
import Palette from './Palette';

export default function TransformCardViewer({ artifact }: { artifact?: Artifact }) {
  const { loadTransformSpec } = usePalette();

  useEffect(() => {
    if (!artifact) return;
    const parsed = getTransformFromArtifact(artifact);
    if (!parsed) return;

    loadTransformSpec(parsed.spec, {
      artifactId: artifact.id ? String(artifact.id) : undefined,
      title: parsed.title,
      savedHash: computeTransformHash(parsed.spec),
      kind: parsed.kind,
      subtype: parsed.subtype,
      run: parsed.run,
    });
  }, [artifact, loadTransformSpec]);

  return <Palette />;
}
