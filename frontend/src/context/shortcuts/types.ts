import type { KeyboardEvent as ReactKeyboardEvent } from 'react';

export type ShortcutCombo = string;

export interface ShortcutRegistrationOptions {
  description?: string;
  order?: number;
  allowInInputs?: boolean;
}

export interface ShortcutRegistration {
  /** Unique identifier for this shortcut (global scope). */
  id: string;
  /** Primary label shown in the shortcuts dialog. */
  label: string;
  /** Logical group bucket (e.g. "General", "Workspace"). */
  group: string;
  /** Optional display title for the group; falls back to `group`. */
  groupTitle?: string;
  /** Ordering priority for the group. */
  groupOrder?: number;
  /** One or more key combinations that trigger this shortcut. */
  combos: ShortcutCombo[];
  /** Optional side-effect when the shortcut is triggered. */
  handler?: (event: KeyboardEvent | ReactKeyboardEvent) => void;
  options?: ShortcutRegistrationOptions;
}

export interface ShortcutEntry {
  id: string;
  label: string;
  description?: string;
  combos: ShortcutCombo[];
  order: number;
}

export interface ShortcutGroup {
  id: string;
  title: string;
  order: number;
  shortcuts: ShortcutEntry[];
}

export interface ShortcutsContextValue {
  registerShortcut: (registration: ShortcutRegistration) => () => void;
  groups: ShortcutGroup[];
  openDialog: () => void;
  closeDialog: () => void;
  toggleDialog: () => void;
  isDialogOpen: boolean;
}
