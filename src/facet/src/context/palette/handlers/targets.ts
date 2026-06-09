import { PaletteState } from '../palette.types';

export async function targetsHandler(state: PaletteState): Promise<PaletteState> {
  // Targets panel data is already in state.panelData.targets
  // Handler does nothing - the panel data IS the targets
  return state;
}
