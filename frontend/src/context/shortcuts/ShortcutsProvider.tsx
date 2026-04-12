import { useCallback, useEffect, useMemo, useRef, useState, type PropsWithChildren } from 'react';
import type { ShortcutRegistration, ShortcutEntry, ShortcutGroup, ShortcutsContextValue } from './types';
import { ShortcutsContext } from './ShortcutContext';
import {
  isEditableTarget,
  isMacPlatform,
  matchesParsedCombo,
  parseCombo,
} from './shortcut-utils';

const DEFAULT_GROUP_ORDER = 100;
const DEFAULT_SHORTCUT_ORDER = 1000;

interface HandlerEntry {
  id: string;
  combos: ReturnType<typeof parseCombo>[];
  handler?: (event: KeyboardEvent) => void;
  allowInInputs: boolean;
}
type GroupState = ShortcutGroup;

function sortGroups(groups: Record<string, GroupState>): ShortcutGroup[] {
  return Object.values(groups)
    .map((group) => ({
      ...group,
      shortcuts: [...group.shortcuts].sort((a, b) => {
        if (a.order !== b.order) return a.order - b.order;
        return a.label.localeCompare(b.label);
      }),
    }))
    .sort((a, b) => {
      if (a.order !== b.order) return a.order - b.order;
      return a.title.localeCompare(b.title);
    });
}

export function ShortcutsProvider({ children }: PropsWithChildren) {
  const [groups, setGroups] = useState<Record<string, GroupState>>({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const handlersRef = useRef<Map<string, HandlerEntry>>(new Map());
  const platformIsMacRef = useRef<boolean>(isMacPlatform());

  useEffect(() => {
    platformIsMacRef.current = isMacPlatform();
  }, []);

  const registerShortcut = useCallback((registration: ShortcutRegistration) => {
    const {
      id,
      label,
      group,
      groupTitle,
      groupOrder,
      combos,
      handler,
      options,
    } = registration;

    if (!id) {
      throw new Error('Shortcut registration requires an id');
    }
    if (!combos || combos.length === 0) {
      throw new Error(`Shortcut registration "${id}" must include at least one combo`);
    }

    const shortcutEntry: ShortcutEntry = {
      id,
      label,
      description: options?.description,
      combos,
      order: options?.order ?? DEFAULT_SHORTCUT_ORDER,
    };

  const parsedCombos = combos.map((combo) => parseCombo(combo));
    const allowInInputs = options?.allowInInputs ?? false;

    setGroups((prev) => {
      const next = { ...prev };
      const existing = next[group];
      const groupState: GroupState = existing
        ? {
            ...existing,
            title: groupTitle ?? existing.title,
            order: groupOrder ?? existing.order,
            shortcuts: existing.shortcuts.filter((shortcut) => shortcut.id !== id),
          }
        : {
            id: group,
            title: groupTitle ?? group,
            order: groupOrder ?? DEFAULT_GROUP_ORDER,
            shortcuts: [],
          };

      groupState.shortcuts = [...groupState.shortcuts, shortcutEntry];
      next[group] = groupState;
      return next;
    });

    handlersRef.current.set(id, {
      id,
      combos: parsedCombos,
      handler: handler as ((event: KeyboardEvent) => void) | undefined,
      allowInInputs,
    });

    return () => {
      setGroups((prev) => {
        const next = { ...prev };
        const targetGroup = next[group];
        if (!targetGroup) return prev;
        const filteredShortcuts = targetGroup.shortcuts.filter((shortcut) => shortcut.id !== id);
        if (filteredShortcuts.length === 0) {
          delete next[group];
        } else {
          next[group] = {
            ...targetGroup,
            shortcuts: filteredShortcuts,
          };
        }
        return next;
      });

      handlersRef.current.delete(id);
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat) {
        return;
      }

      const isEditable = isEditableTarget(event.target);
      const mac = platformIsMacRef.current;

      for (const entry of handlersRef.current.values()) {
        if (!entry.allowInInputs && isEditable) {
          continue;
        }

        const match = entry.combos.some((combo) => matchesParsedCombo(event, combo, mac));
        if (!match) continue;

        if (entry.handler) {
          entry.handler(event);
        }

        if (!event.defaultPrevented) {
          // Do not break to allow other handlers if they did not handle it
          continue;
        }

        break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    const unregister = registerShortcut({
      id: 'shortcuts:open-dialog',
      label: 'Open keyboard shortcuts',
      group: 'general',
      groupTitle: 'General',
      groupOrder: 0,
      combos: ['?','mod+/'],
      handler: (event) => {
        event.preventDefault();
        setDialogOpen(true);
      },
      options: {
        description: 'Show the keyboard shortcuts reference',
      },
    });

    return unregister;
  }, [registerShortcut]);

  const value: ShortcutsContextValue = useMemo(() => ({
    registerShortcut,
    groups: sortGroups(groups),
    openDialog: () => setDialogOpen(true),
    closeDialog: () => setDialogOpen(false),
    toggleDialog: () => setDialogOpen((prev) => !prev),
    isDialogOpen: dialogOpen,
  }), [registerShortcut, groups, dialogOpen]);

  return (
    <ShortcutsContext.Provider value={value}>
      {children}
    </ShortcutsContext.Provider>
  );
}
