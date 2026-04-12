import { createStrictContext } from '../../utils/createStrictContext';
import { PaletteState, PanelData, PanelKey, PanelStatus } from './palette.types';
import type { TransformKind, TransformRunConfig, TransformSpec } from './order.types';

export type TransformMeta = {
  artifactId?: string;
  title?: string;
  savedHash?: string;
  kind?: TransformKind | string;
  subtype?: string;
  run?: TransformRunConfig;
};

export type PaletteOrderMeta = TransformMeta;


export interface PaletteContextType {
  state: PaletteState;

  updateState: (updater: (prev: PaletteState) => PaletteState) => void;

  updatePanelData: <K extends PanelKey>(
    panelKey: K,
    updater: (prev: PanelData[K]) => PanelData[K]
  ) => void;

  nextStep: PanelKey;
  breakpoints: Set<PanelKey>;
  visiblePanels: PanelKey[];
  maximizedPanels: PanelKey[];
  panelStatus: Record<PanelKey, PanelStatus>;

  runFrom: (panelKey: PanelKey) => Promise<void>;
  resume: () => Promise<void>;
  clear: () => void;

  addPause: (panelKey: PanelKey) => void;
  removePause: (panelKey: PanelKey) => void;

  showPanel: (panelKey: PanelKey) => void;
  hidePanel: (panelKey: PanelKey) => void;
  maximizePanel: (panelKey: PanelKey) => void;
  minimizePanel: (panelKey: PanelKey) => void;
  updatePanelStatus: (panelKey: PanelKey, status: PanelStatus) => void;

  transform: null | TransformMeta;

  setTransform: (meta: PaletteContextType['transform']) => void;
  loadTransformSpec: (
    spec: TransformSpec,
    meta?: TransformMeta
  ) => void;
}

export const [PaletteContext, usePalette] =
  createStrictContext<PaletteContextType>('PaletteContext');
