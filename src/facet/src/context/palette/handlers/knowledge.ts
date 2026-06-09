import { PaletteState } from '../palette.types';

export async function knowledgeHandler(state: PaletteState): Promise<PaletteState> {
  // Knowledge panel data is already in state.panelData.knowledge
  // Handler does nothing - the panel data IS the knowledge
  return state;
}
