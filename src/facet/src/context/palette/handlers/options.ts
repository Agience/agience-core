import { PaletteState } from '../palette.types';

export async function optionsHandler(state: PaletteState): Promise<PaletteState> {
  // Options panel data is already in state.panelData.options
  // Handler does nothing - the panel data IS the options
  return state;
}
