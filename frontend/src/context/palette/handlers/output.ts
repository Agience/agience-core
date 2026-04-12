import { PaletteState } from "../palette.types";

export async function outputHandler(
  state: PaletteState,
  deps: {
    addArtifact: (desc: string, content: string) => Promise<{ id?: string } | null>;
  }
): Promise<PaletteState> {
  const outputArtifacts = state.panelData.output.artifacts;
  const createdIds: string[] = [];
  for (const artifact of outputArtifacts) {
    const created = await deps.addArtifact(artifact.context ?? "", artifact.content ?? "");
    if (created?.id) createdIds.push(String(created.id));
  }

  return state;
}
