import { useCallback, useEffect, useRef, useState } from 'react';
import type { Artifact } from '@/context/workspace/workspace.types';
import type { ViewState } from '@/registry/content-types';
import { useWorkspace } from '@/hooks/useWorkspace';
import { useDebouncedSave } from '@/hooks/useDebouncedSave';

/**
 * Text/plain viewer — seamless inline view/edit.
 *
 * View and edit modes are visually identical: same textarea element,
 * same font, same padding. Only `readOnly` toggles. Auto-saves on edit
 * with debounce — no Save/Cancel buttons.
 *
 * See `.dev/features/viewer-ux-guidelines.md` for the full contract.
 */
export default function TextPlainViewer({
  artifact,
  state = 'view',
}: {
  artifact: Artifact;
  mode?: string;
  state?: ViewState;
  onOpenCollection?: (collectionId: string) => void;
  onOpenArtifact?: (artifact: Artifact) => void;
}) {
  const isEditing = state === 'edit';
  const { updateArtifact } = useWorkspace();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Local content mirrors artifact.content; reset when artifact changes externally.
  const [localContent, setLocalContent] = useState(artifact.content ?? '');
  useEffect(() => {
    if (!isEditing) {
      setLocalContent(artifact.content ?? '');
    }
  }, [artifact.content, isEditing]);

  // When entering edit mode, sync and focus.
  useEffect(() => {
    if (isEditing) {
      setLocalContent(artifact.content ?? '');
      // Defer focus so the textarea is mounted and interactive.
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }, [isEditing]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced auto-save (only while editing and content has changed).
  const { isSaving, lastSaved } = useDebouncedSave(localContent, {
    delay: 1500,
    onSave: async (value) => {
      if (!artifact.id) return;
      await updateArtifact({ id: String(artifact.id), content: value });
    },
    enabled: isEditing && localContent !== (artifact.content ?? ''),
  });

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setLocalContent(e.target.value);
    },
    [],
  );

  // Word / character counts for the footer.
  const displayContent = isEditing ? localContent : (artifact.content ?? '');
  const charCount = displayContent.length;
  const wordCount = displayContent.trim() ? displayContent.trim().split(/\s+/).length : 0;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Content — single textarea for both modes */}
      <div className="flex-1 overflow-hidden">
        <textarea
          ref={textareaRef}
          value={displayContent}
          onChange={handleChange}
          readOnly={!isEditing}
          placeholder={isEditing ? 'Start typing…' : ''}
          spellCheck={isEditing}
          className={[
            'w-full h-full resize-none border-0 outline-none bg-white',
            'px-5 py-4 text-sm text-gray-800 leading-relaxed',
            // Subtle focus ring only in edit mode
            isEditing ? 'focus:ring-0' : 'cursor-default',
          ].join(' ')}
          style={{ fontFamily: 'inherit' }}
        />
      </div>

      {/* Footer — subtle status indicators */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-1 border-t border-gray-100 text-[11px] text-gray-400 select-none">
        <span>
          {charCount > 0
            ? `${wordCount} word${wordCount !== 1 ? 's' : ''} · ${charCount} char${charCount !== 1 ? 's' : ''}`
            : '\u00A0'}
        </span>
        <span>
          {isSaving
            ? 'Saving…'
            : lastSaved
              ? 'Saved'
              : '\u00A0'}
        </span>
      </div>
    </div>
  );
}