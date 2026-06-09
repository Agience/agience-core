import { PaletteState } from '../palette.types';

export async function toolsHandler(state: PaletteState, user_id: string): Promise<PaletteState> {
  void user_id;
  // MVP: Tools panel is configuration only.
  // Do not generate synthetic "knowledge" artifacts; the selected tools are already in state.panelData.tools.
  return state;
}
