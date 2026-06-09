import { useEffect, useRef } from 'react';
import MDEditor from '@uiw/react-md-editor';

interface MarkdownEditorProps {
  content: string;
  onChange: (newContent: string) => void;
  onBlur?: () => void;
  onEscape?: () => void;
  autoFocus?: boolean;
}

/**
 * Markdown editor component for inline editing
 * Uses @uiw/react-md-editor with side-by-side preview
 * 
 * @param content - Current markdown content
 * @param onChange - Callback fired on every content change
 * @param onBlur - Optional callback when editor loses focus
 * @param onEscape - Optional callback when Escape key is pressed
 * @param autoFocus - Whether to auto-focus editor on mount (default: true)
 */
export function MarkdownEditor({
  content,
  onChange,
  onBlur,
  onEscape,
  autoFocus = true,
}: MarkdownEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);

  // Auto-focus on mount
  useEffect(() => {
    if (autoFocus && editorRef.current) {
      // MDEditor doesn't expose a focus method, so we find the textarea
      const textarea = editorRef.current.querySelector('textarea');
      if (textarea) {
        textarea.focus();
        // Move cursor to end of content
        textarea.setSelectionRange(content.length, content.length);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFocus]); // Only run on mount, content.length intentionally omitted

  // Handle Escape key
  useEffect(() => {
    if (!onEscape) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onEscape();
      }
    };

    const editorElement = editorRef.current;
    if (editorElement) {
      editorElement.addEventListener('keydown', handleKeyDown);
      return () => {
        editorElement.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [onEscape]);

  // Handle blur
  const handleBlur = () => {
    if (onBlur) {
      onBlur();
    }
  };

  return (
    <div 
      ref={editorRef}
      onBlur={handleBlur}
      className="markdown-editor-wrapper"
    >
      <MDEditor
        value={content}
        onChange={(value) => onChange(value || '')}
        preview="live"
        height={400}
        visibleDragbar={false}
        hideToolbar={false}
        textareaProps={{
          placeholder: 'Enter markdown content...',
        }}
      />
    </div>
  );
}
