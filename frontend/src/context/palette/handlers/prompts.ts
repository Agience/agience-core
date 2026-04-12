import { PaletteState } from '../palette.types';

export async function promptsHandler(state: PaletteState): Promise<PaletteState> {
  const panel = state.panelData.prompts;
  const selectedArtifact = panel.artifacts.find((c) => c.id === panel.selectedId);

  if (!selectedArtifact) return state;

  return {
    ...state,
    panelData: {
      ...state.panelData,
      instructions: {
        ...state.panelData.instructions,
        artifacts: [selectedArtifact],
      },
    },
  };
}
