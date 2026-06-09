import { useMemo } from 'react';
import { MarkdownEditor } from './MarkdownEditor';

interface EditorFactoryProps {
  content: string;
  mime?: string;
  filename?: string;
  onChange: (newContent: string) => void;
  onBlur?: () => void;
  onEscape?: () => void;
  autoFocus?: boolean;
}

/**
 * Determines content type from MIME, filename, or content structure
 * Reuses logic from ContentRenderer for consistency
 */
function detectContentType(content: string, mime?: string, filename?: string): string {
  // Determine content type from MIME or filename.
  // Only match base MIME types (e.g. application/json), NOT structured
  // suffixes like +json which appear in vendor types such as
  // application/vnd.agience.agent+json.
  if (mime) {
    if (mime === 'application/json' || mime === 'text/json') return 'json';
    if (mime.includes('javascript')) return 'javascript';
    if (mime.includes('python')) return 'python';
    if (mime.includes('xml') || mime.includes('html')) return 'xml';
    if (mime.includes('markdown')) return 'markdown';
    if (mime.includes('yaml')) return 'yaml';
  }
  
  if (filename) {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (ext === 'json') return 'json';
    if (ext === 'js' || ext === 'jsx' || ext === 'ts' || ext === 'tsx') return 'javascript';
    if (ext === 'py') return 'python';
    if (ext === 'xml' || ext === 'html') return 'xml';
    if (ext === 'md' || ext === 'markdown') return 'markdown';
    if (ext === 'yaml' || ext === 'yml') return 'yaml';
  }
  
  // Try to detect JSON from content structure
  if (content.trim().startsWith('{') || content.trim().startsWith('[')) {
    try {
      JSON.parse(content);
      return 'json';
    } catch {
      // Not valid JSON
    }
  }
  
  return 'text';
}

/**
 * EditorFactory - Routes content to appropriate MIME-specific editor
 * 
 * Currently supports:
 * - Markdown: MarkdownEditor (@uiw/react-md-editor)
 * - JSON/Code/Text: Fallback to MarkdownEditor (TODO: Add Monaco editor)
 * 
 * Future editors:
 * - JsonEditor: Monaco with validation
 * - CodeEditor: Monaco with syntax highlighting
 * - PlainTextEditor: Simple textarea
 */
export function EditorFactory({
  content,
  mime,
  filename,
  onChange,
  onBlur,
  onEscape,
  autoFocus = true,
}: EditorFactoryProps) {
  const contentType = useMemo(
    () => detectContentType(content, mime, filename),
    [content, mime, filename]
  );

  // For now, route all editable content to MarkdownEditor
  // TODO: Add specialized editors for JSON, code, plain text
  switch (contentType) {
    case 'markdown':
    case 'json':
    case 'javascript':
    case 'python':
    case 'xml':
    case 'yaml':
    case 'text':
    default:
      return (
        <MarkdownEditor
          content={content}
          onChange={onChange}
          onBlur={onBlur}
          onEscape={onEscape}
          autoFocus={autoFocus}
        />
      );
  }
}
