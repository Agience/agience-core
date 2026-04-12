import { PanelKey } from '../../context/palette/palette.types';

import {
  InputPanel,
  Resources,
  Context,
  Prompts,
  Instructions,
  Tools,
  Knowledge,
  Agent,
  Targets,
  OutputPanel,
} from './panels';

export const PALETTE_PANELS = [
  // Config tab
  { key: 'resources' as PanelKey, label: 'Resources', controls: ['pause'], content: <Resources /> },
  { key: 'tools' as PanelKey, label: 'Knowledge', controls: ['pause'], content: <Tools /> },
  { key: 'prompts' as PanelKey, label: 'Prompts', controls: ['pause'], content: <Prompts /> },
  { key: 'input' as PanelKey , label: 'Input', controls: ['pause'], content: <InputPanel /> },
  { key: 'targets' as PanelKey , label: 'Targets', controls: ['pause'], content: <Targets /> },

  // Inspect tab
  { key: 'context' as PanelKey, label: 'Resolved Sources', controls: ['pause'], content: <Context /> },
  { key: 'instructions' as PanelKey, label: 'Compiled Instructions', controls: ['pause'], content: <Instructions /> },
  { key: 'knowledge' as PanelKey, label: 'Resolved Knowledge', controls: ['pause'], content: <Knowledge /> },
  { key: 'output' as PanelKey, label: 'Results', controls: ['pause'], content: <OutputPanel /> },

  // Execution step (kept, but hidden by default in tabs)
  { key: 'agent' as PanelKey, label: 'Agent', controls: ['pause'], content: <Agent /> }
] as const;
