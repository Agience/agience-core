import { useWorkspace } from '../workspace/WorkspaceContext';
import { useAuth } from '../../hooks/useAuth';
import { useWorkspaces } from '../../context/workspaces/WorkspacesContext';
import { PaletteState, PanelKey } from './palette.types';
import {
  contextHandler,
  inputHandler,
  resourcesHandler,
  promptsHandler,
  instructionsHandler,
  toolsHandler,
  knowledgeHandler,
  optionsHandler,
  agentHandler,
  targetsHandler,
  outputHandler
} from './handlers';

export const STEP_KEYS: PanelKey[] = [
  'input',
  'resources',
  'context',
  'prompts',
  'instructions',
  'tools',
  'knowledge',
  'options',
  'agent',
  'targets',
  'output',
];

export function useStepHandlers(): Record<PanelKey, (state: PaletteState) => Promise<PaletteState>> {
  const { createArtifact, selectedArtifactIds, refreshArtifacts } = useWorkspace();
  const { activeWorkspace } = useWorkspaces();
  const user_id = useAuth().user?.id ?? '';
  const workspaceId = activeWorkspace?.id ?? '';

  // Wrap createArtifact so outputHandler can capture created IDs.
  const addArtifactFromOutput = async (desc: string, content: string) => {
    const created = await createArtifact({
      content,
      context: JSON.stringify({
        content_type: 'text/plain',
        type: 'palette-output',
        title: (desc || '').trim() || 'Output',
      }),
    });
    return created ? { id: created.id } : null;
  };

  return {
    input: inputHandler,
    resources: (state) => resourcesHandler(state, { workspaceId }),
    context: contextHandler,
    prompts: promptsHandler,
    instructions: instructionsHandler,
    tools: (state) => toolsHandler(state, user_id),
    knowledge: knowledgeHandler,
    options: optionsHandler,
    agent: async (state) => {
      const next = await agentHandler(state, {
        userId: user_id,
        workspaceId,
        selectedArtifactIds,
      });
      if (workspaceId) {
        await refreshArtifacts(workspaceId);
      }
      return next;
    },
    targets: targetsHandler,
    output: (state) => outputHandler(state, { addArtifact: addArtifactFromOutput }),
  };
}
