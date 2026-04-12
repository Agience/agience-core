import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import MarkdownCardViewer from './viewer';

const fakeEditor = {
  commands: {
    setContent: vi.fn(),
    focus: vi.fn(),
  },
  chain: () => ({
    focus: () => ({
      toggleHeading: () => ({ run: vi.fn() }),
      toggleBold: () => ({ run: vi.fn() }),
      toggleItalic: () => ({ run: vi.fn() }),
      toggleStrike: () => ({ run: vi.fn() }),
      toggleCode: () => ({ run: vi.fn() }),
      toggleBulletList: () => ({ run: vi.fn() }),
      toggleOrderedList: () => ({ run: vi.fn() }),
      toggleBlockquote: () => ({ run: vi.fn() }),
      toggleCodeBlock: () => ({ run: vi.fn() }),
      setHorizontalRule: () => ({ run: vi.fn() }),
      undo: () => ({ run: vi.fn() }),
      redo: () => ({ run: vi.fn() }),
    }),
  }),
  isActive: vi.fn(() => false),
  can: () => ({ undo: () => true, redo: () => true }),
  storage: {
    markdown: {
      getMarkdown: () => '# Title\n\nBody',
    },
  },
  setEditable: vi.fn(),
  isFocused: false,
};

vi.mock('@tiptap/react', () => ({
  useEditor: (options?: { onCreate?: ({ editor }: { editor: typeof fakeEditor }) => void }) => {
    options?.onCreate?.({ editor: fakeEditor });
    return fakeEditor;
  },
  EditorContent: () => <div data-testid="editor-content">editor-content</div>,
}));

vi.mock('@tiptap/starter-kit', () => ({
  default: {},
}));

vi.mock('@tiptap/extension-placeholder', () => ({
  default: {
    configure: () => ({}),
  },
}));

vi.mock('tiptap-markdown', () => ({
  Markdown: {
    configure: () => ({}),
  },
}));

vi.mock('@/hooks/useWorkspaces', () => ({
  useWorkspaces: () => ({ activeWorkspaceId: 'ws-1' }),
}));

vi.mock('@/hooks/useWorkspace', () => ({
  useWorkspace: () => ({
    artifacts: [
      {
        id: 'markdown-1',
        context: JSON.stringify({ title: 'Untitled Markdown', content_type: 'text/markdown' }),
        content: '# Title\n\nBody',
      },
    ],
    updateArtifact: vi.fn(),
  }),
}));

vi.mock('@/hooks/useDebouncedSave', () => ({
  useDebouncedSave: () => ({
    isSaving: false,
    lastSaved: null,
    resetTracking: () => {},
  }),
}));

vi.mock('@/components/preview/ContentRenderer', () => ({
  ContentRenderer: ({ content, mime }: { content: string; mime?: string }) => (
    <div data-testid="rendered-markdown">{mime}:{content}</div>
  ),
}));

describe('MarkdownCardViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders markdown output in view mode', () => {
    render(
      <MarkdownCardViewer
        artifact={{
          id: 'markdown-1',
          context: JSON.stringify({ title: 'Untitled Markdown', content_type: 'text/markdown' }),
          content: '# Title\n\nBody',
          state: 'committed' as const,
        }}
        state="view"
      />,
    );

    expect(screen.getByTestId('rendered-markdown')).toHaveTextContent('text/markdown:# Title');
    expect(screen.queryByTestId('editor-content')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Title…')).not.toBeInTheDocument();
  });

  it('renders the integrated editor in edit mode', () => {
    render(
      <MarkdownCardViewer
        artifact={{
          id: 'markdown-1',
          context: JSON.stringify({ title: 'Untitled Markdown', content_type: 'text/markdown' }),
          content: '# Title\n\nBody',
          state: 'committed' as const,
        }}
        state="edit"
      />,
    );

    expect(screen.getByTestId('editor-content')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Title…')).toBeInTheDocument();
    expect(screen.queryByTestId('rendered-markdown')).not.toBeInTheDocument();
  });
});