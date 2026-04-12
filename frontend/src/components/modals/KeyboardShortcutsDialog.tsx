import { Fragment, useMemo } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Separator } from '@/components/ui/separator';
import { formatShortcutCombo } from '@/context/shortcuts/shortcut-utils';
import { useShortcuts } from '@/context/shortcuts/useShortcuts';

export default function KeyboardShortcutsDialog() {
  const { groups, isDialogOpen, closeDialog, openDialog } = useShortcuts();
  const keyClass = 'px-2 py-1 text-xs bg-gray-100 border border-gray-300 rounded font-medium text-gray-700';

  const openCombos = useMemo(
    () => [formatShortcutCombo('?'), formatShortcutCombo('mod+/')],
    []
  );

  const handleOpenChange = (open: boolean) => {
    if (open) {
      openDialog();
    } else {
      closeDialog();
    }
  };

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            Speed through curation with these shortcuts. Press{' '}
            <span className="inline-flex items-center gap-1">
              {openCombos[0].map((key) => (
                <kbd key={`hint-${key}`} className={keyClass}>
                  {key}
                </kbd>
              ))}
            </span>{' '}
            or{' '}
            <span className="inline-flex items-center gap-1">
              {openCombos[1].map((key) => (
                <kbd key={`hint-alt-${key}`} className={keyClass}>
                  {key}
                </kbd>
              ))}
            </span>{' '}
            anytime to reopen this panel.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto pr-1">
          {groups.length === 0 ? (
            <p className="text-sm text-muted-foreground">No shortcuts registered yet.</p>
          ) : (
            groups.map((group, index) => (
              <Fragment key={group.id}>
                <div className="py-3">
                  <h3 className="text-sm font-semibold text-foreground mb-2">{group.title}</h3>
                  <ul className="space-y-2">
                    {group.shortcuts.map((shortcut) => (
                      <li key={shortcut.id} className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <p className="text-sm font-medium text-foreground">{shortcut.label}</p>
                          {shortcut.description ? (
                            <p className="text-xs text-muted-foreground mt-0.5">{shortcut.description}</p>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-2 justify-end">
                          {shortcut.combos.map((combo) => (
                            <span key={`${shortcut.id}-${combo}`} className="inline-flex items-center gap-1">
                              {formatShortcutCombo(combo).map((keyPart) => (
                                <kbd key={keyPart} className={keyClass}>
                                  {keyPart}
                                </kbd>
                              ))}
                            </span>
                          ))}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
                {index < groups.length - 1 ? <Separator className="my-2" /> : null}
              </Fragment>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
