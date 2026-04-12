// src/context/palette/handlers/instructions.ts
import { PaletteState } from '../palette.types';
import { Artifact } from '../../workspace/workspace.types';

const CHUNK_SIZE = 500;

export async function instructionsHandler(state: PaletteState): Promise<PaletteState> {
  const chunks: Artifact[] = [];
  const inputArtifacts = state.panelData.input.artifacts;

  for (const input of inputArtifacts) {
    const text = input.content || '';
    for (let i = 0; i < text.length; i += CHUNK_SIZE) {
      chunks.push({
        id: `chunk-${input.id}-${i}`,
        context: JSON.stringify({
          content_type: 'text/plain',
          type: 'chunk',
          title: `Chunk ${i / CHUNK_SIZE + 1}`,
          source_artifact_id: String(input.id ?? ''),
        }),
        content: text.slice(i, i + CHUNK_SIZE),
        state: 'draft',
      });
    }
  }

  return {
    ...state,
    panelData: {
      ...state.panelData,
      instructions: {
        ...state.panelData.instructions,
        artifacts: chunks,
      },
    },
  };
}
