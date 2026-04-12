import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import { Markdown } from 'tiptap-markdown';
import {
  Bold, Italic, Strikethrough, Code, Code2,
  Heading1, Heading2, Heading3,
  List, ListOrdered, Quote, Minus,
  Undo2, Redo2,
} from 'lucide-react';
import { useWorkspace } from '@/hooks/useWorkspace';
import { useDebouncedSave } from '@/hooks/useDebouncedSave';
import { useArtifactContent } from '@/hooks/useArtifactContent';
import { ContentRenderer } from '@/components/preview/ContentRenderer';
import { safeParseArtifactContext, stringifyArtifactContext } from '@/utils/artifactContext';
import type { Artifact } from '@/context/workspace/workspace.types';
import type { ViewMode, ViewState } from '@/registry/content-types';

// ── Toolbar helpers ────────────────────────────────────────────────────────

function ToolbarBtn({
  onClick,
  active,
  disabled,
  title,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => { e.preventDefault(); onClick(); }}
      disabled={disabled}
      title={title}
      className={`p-1.5 rounded text-sm transition-colors disabled:opacity-30 ${
        active
          ? 'bg-gray-200 text-gray-900'
          : 'text-gray-500 hover:bg-gray-100 hover:text-gray-800'
      }`}
    >
      {children}
    </button>
  );
}

function Sep() {
  return <div className="w-px h-4 bg-gray-200 mx-1 flex-shrink-0" />;
}

// ── Main viewer component ─────────────────────────────────────────────────

interface Props {
  artifact: Artifact;
  mode?: ViewMode;
  state?: ViewState;
  onOpenCollection?: (collectionId: string) => void;
}

export default function MarkdownCardViewer({ artifact, state = 'view' }: Props) {
  const { artifacts, updateArtifact } = useWorkspace();
  const { content: resolvedContent, loading: contentLoading } = useArtifactContent(artifact);

  const isReadOnly = useMemo(
    () => !artifacts.find((c) => String(c.id) === String(artifact.id)),
    [artifacts, artifact.id],
  );

  const isEditing = state === 'edit' && !isReadOnly;

  const ctx = useMemo(
    () => safeParseArtifactContext(artifact.context),
    [artifact.context],
  );

  // Local state for debounced saves
  const [localContent, setLocalContent] = useState(resolvedContent);
  const [localTitle, setLocalTitle] = useState(
    (ctx.title as string | undefined) || (ctx.filename as string | undefined) || '',
  );

  // Prevent editor reset while user is actively typing
  const lastSyncedRef = useRef<string>(resolvedContent);
  const editorInitialized = useRef(false);

  // ── TipTap editor ───────────────────────────────────────────────────────

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder: 'Start writing…' }),
      Markdown.configure({
        html: false,
        transformPastedText: true,
        transformCopiedText: true,
      }),
    ],
    content: '',
    editable: isEditing,
    onCreate: ({ editor }) => {
      editor.commands.setContent(resolvedContent);
      lastSyncedRef.current = resolvedContent;
      editorInitialized.current = true;
    },
    onUpdate: ({ editor }) => {
      if (!editorInitialized.current) return;
      const md: string = (editor.storage as unknown as { markdown: { getMarkdown: () => string } }).markdown.getMarkdown();
      setLocalContent(md);
    },
  });

  // Once S3-fetched content arrives, initialise the editor with it.
  useEffect(() => {
    if (!editor || contentLoading) return;
    if (editorInitialized.current) {
      // External update (e.g. revert) — only apply if the editor is not focused.
      if (editor.isFocused) return;
      if (resolvedContent !== lastSyncedRef.current) {
        editor.commands.setContent(resolvedContent);
        setLocalContent(resolvedContent);
        lastSyncedRef.current = resolvedContent;
      }
    } else {
      // First initialisation after async fetch.
      editor.commands.setContent(resolvedContent);
      setLocalContent(resolvedContent);
      lastSyncedRef.current = resolvedContent;
      editorInitialized.current = true;
    }
  }, [resolvedContent, contentLoading, editor]);

  // Keep editable state in sync
  useEffect(() => {
    if (!editor) return;
    editor.setEditable(isEditing);
  }, [isEditing, editor]);

  // ── Autosave content ───────────────────────────────────────────────────

  const saveContent = useCallback(
    async (val: string) => {
      if (!artifact || isReadOnly) return;
      await updateArtifact({ id: String(artifact.id), content: val });
      lastSyncedRef.current = val;
    },
    [artifact, isReadOnly, updateArtifact],
  );

  const { isSaving: isContentSaving, lastSaved: contentSaved } = useDebouncedSave(
    localContent,
    {
      delay: 1500,
      onSave: saveContent,
      enabled: !isReadOnly && localContent !== resolvedContent,
    },
  );

  // ── Autosave title ─────────────────────────────────────────────────────

  const originalTitle =
    (ctx.title as string | undefined) || (ctx.filename as string | undefined) || '';

  const saveTitle = useCallback(
    async (val: string) => {
      if (!artifact || isReadOnly) return;
      const updated = { ...ctx, title: val };
      await updateArtifact({
        id: String(artifact.id),
        context: stringifyArtifactContext(updated),
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [artifact, isReadOnly, updateArtifact],
  );

  useDebouncedSave(localTitle, {
    delay: 1500,
    onSave: saveTitle,
    enabled: !isReadOnly && localTitle !== originalTitle,
  });

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-white text-gray-900 overflow-hidden" data-color-mode="light">

      {/* ── Formatting toolbar ─────────────────────────────────────────── */}
      {editor && isEditing && (
        <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-gray-100 bg-gray-50/80 flex-shrink-0 flex-wrap select-none">

          {/* Headings */}
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
            active={editor.isActive('heading', { level: 1 })}
            disabled={isReadOnly}
            title="Heading 1"
          ><Heading1 className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            active={editor.isActive('heading', { level: 2 })}
            disabled={isReadOnly}
            title="Heading 2"
          ><Heading2 className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
            active={editor.isActive('heading', { level: 3 })}
            disabled={isReadOnly}
            title="Heading 3"
          ><Heading3 className="w-4 h-4" /></ToolbarBtn>

          <Sep />

          {/* Inline marks */}
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleBold().run()}
            active={editor.isActive('bold')}
            disabled={isReadOnly}
            title="Bold (Ctrl+B)"
          ><Bold className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleItalic().run()}
            active={editor.isActive('italic')}
            disabled={isReadOnly}
            title="Italic (Ctrl+I)"
          ><Italic className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleStrike().run()}
            active={editor.isActive('strike')}
            disabled={isReadOnly}
            title="Strikethrough"
          ><Strikethrough className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleCode().run()}
            active={editor.isActive('code')}
            disabled={isReadOnly}
            title="Inline code"
          ><Code className="w-4 h-4" /></ToolbarBtn>

          <Sep />

          {/* Block types */}
          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            active={editor.isActive('bulletList')}
            disabled={isReadOnly}
            title="Bullet list"
          ><List className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            active={editor.isActive('orderedList')}
            disabled={isReadOnly}
            title="Numbered list"
          ><ListOrdered className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
            active={editor.isActive('blockquote')}
            disabled={isReadOnly}
            title="Blockquote"
          ><Quote className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().toggleCodeBlock().run()}
            active={editor.isActive('codeBlock')}
            disabled={isReadOnly}
            title="Code block"
          ><Code2 className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().setHorizontalRule().run()}
            disabled={isReadOnly}
            title="Divider"
          ><Minus className="w-4 h-4" /></ToolbarBtn>

          <Sep />

          {/* History */}
          <ToolbarBtn
            onClick={() => editor.chain().focus().undo().run()}
            disabled={isReadOnly || !editor.can().undo()}
            title="Undo (Ctrl+Z)"
          ><Undo2 className="w-4 h-4" /></ToolbarBtn>

          <ToolbarBtn
            onClick={() => editor.chain().focus().redo().run()}
            disabled={isReadOnly || !editor.can().redo()}
            title="Redo (Ctrl+Y)"
          ><Redo2 className="w-4 h-4" /></ToolbarBtn>

          {/* Save status */}
          <div className="ml-auto flex items-center pl-2">
            {isContentSaving && (
              <span className="text-xs text-gray-400">Saving…</span>
            )}
            {!isContentSaving && contentSaved && (
              <span className="text-xs text-gray-300">Saved</span>
            )}
          </div>
        </div>
      )}

      {/* ── Title ──────────────────────────────────────────────────────── */}
      <div className="px-5 pt-4 pb-1 flex-shrink-0">
        {!isEditing ? (
          <h2 className="text-xl font-semibold text-gray-900 leading-snug">
            {localTitle || 'Untitled'}
          </h2>
        ) : (
          <input
            type="text"
            value={localTitle}
            onChange={(e) => setLocalTitle(e.target.value)}
            placeholder="Title…"
            className="w-full text-xl font-semibold text-gray-900 placeholder-gray-300 bg-transparent border-none outline-none leading-snug"
          />
        )}
      </div>

      {/* ── WYSIWYG body ───────────────────────────────────────────────── */}
      {isEditing ? (
        <div
          className="flex-1 overflow-y-auto px-5 pb-6 cursor-text"
          onClick={() => editor?.commands.focus()}
        >
          <EditorContent
            editor={editor}
            className="tiptap-editor prose prose-sm max-w-none
              prose-headings:font-semibold prose-headings:text-gray-900
              prose-p:text-gray-800 prose-p:leading-relaxed
              prose-strong:font-semibold prose-strong:text-gray-900
              prose-code:text-pink-600 prose-code:bg-pink-50 prose-code:px-1 prose-code:rounded prose-code:text-[0.85em] prose-code:font-mono
              prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:rounded-lg
              prose-blockquote:border-l-4 prose-blockquote:border-gray-300 prose-blockquote:text-gray-600 prose-blockquote:not-italic
              prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5
              prose-hr:border-gray-200"
          />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-5 pb-6">
          <ContentRenderer content={localContent || resolvedContent} mime="text/markdown" />
        </div>
      )}
    </div>
  );
}
