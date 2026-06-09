import { PaletteState } from '../palette.types';

export async function inputHandler(state: PaletteState): Promise<PaletteState> {
  // Input handler does nothing - the panel data IS the input
  return state;
}
