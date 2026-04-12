// src/components/preview/ContentRenderer.tsx
import { useEffect, useMemo, useState } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import { normalizeContentType } from '@/utils/content-type';

/** Lightweight read-only markdown renderer via TipTap — no dark-mode CSS side-effects. */
function MarkdownRenderer({ content }: { content: string }) {
  const editor = useEditor({
    extensions: [StarterKit, Markdown],
    content,
    editable: false,
    immediatelyRender: false,
  });
  return <EditorContent editor={editor} className="prose prose-sm max-w-none text-gray-900" />;
}

interface ContentRendererProps {
  content: string;
  mime?: string;
  filename?: string;
  uri?: string;
}

/**
 * ContentRenderer - Intelligently renders artifact content based on MIME type
 * 
 * Handles:
 * - Plain text (default)
 * - Code (JSON, JavaScript, Python, etc.)
 * - Markdown (rendered via MDEditor.Markdown)
 * - Images (future: with CDN URLs)
 */
export function ContentRenderer({ content, mime, filename, uri }: ContentRendererProps) {
  const normalizedMime = useMemo(() => normalizeContentType(mime), [mime]);

  const mediaUrl = useMemo(() => {
    const candidate = typeof uri === 'string' && uri.trim() ? uri.trim() : '';
    if (!candidate) return undefined;
    // Only attempt to embed absolute URLs for safety/portability.
    if (candidate.startsWith('http://') || candidate.startsWith('https://')) return candidate;
    return undefined;
  }, [uri]);

  // True when this MIME type is served as a binary media embed (image/video/audio/pdf).
  // Everything else is treated as text and fetched from the URI when content is empty.
  const isMediaType = useMemo(() => {
    if (!normalizedMime) return false;
    return (
      normalizedMime === 'application/pdf' ||
      normalizedMime.startsWith('image/') ||
      normalizedMime.startsWith('video/') ||
      normalizedMime.startsWith('audio/')
    );
  }, [normalizedMime]);

  // When content is empty and a URI is provided for a non-media type, fetch the text.
  const [uriFetchedContent, setUriFetchedContent] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (!mediaUrl || isMediaType || content) {
      setUriFetchedContent(undefined);
      return;
    }
    let cancelled = false;
    fetch(mediaUrl)
      .then((r) => r.text())
      .then((text) => { if (!cancelled) setUriFetchedContent(text); })
      .catch(() => { if (!cancelled) setUriFetchedContent(undefined); });
    return () => { cancelled = true; };
  }, [mediaUrl, isMediaType, content]);

  const effectiveContent = uriFetchedContent ?? content;

  const mediaNode = useMemo(() => {
    if (!mediaUrl || !normalizedMime) return null;

    if (normalizedMime === 'application/pdf') {
      return (
        <div className="w-full">
          <iframe
            src={mediaUrl}
            title={filename ?? 'PDF'}
            className="w-full h-[70vh] rounded border border-gray-200"
          />
        </div>
      );
    }

    if (normalizedMime.startsWith('video/')) {
      return (
        <video
          src={mediaUrl}
          controls
          className="w-full max-h-[70vh] rounded border border-gray-200 bg-black"
        />
      );
    }

    if (normalizedMime.startsWith('audio/')) {
      return (
        <audio
          src={mediaUrl}
          controls
          className="w-full"
        />
      );
    }

    if (normalizedMime.startsWith('image/')) {
      return (
        <img
          src={mediaUrl}
          alt={filename ?? 'Image'}
          className="max-w-full max-h-[70vh] rounded border border-gray-200 object-contain"
        />
      );
    }

    return null;
  }, [mediaUrl, normalizedMime, filename]);

  const contentType = useMemo(() => {
    // Determine content type from MIME or filename.
    // Only match base MIME types (e.g. application/json), NOT structured
    // suffixes like +json which appear in vendor types such as
    // application/vnd.agience.agent+json — those are plain-text content
    // that should not be rendered as code blocks.
    if (normalizedMime) {
      if (normalizedMime === 'application/json' || normalizedMime === 'text/json') return 'json';
      if (normalizedMime.includes('javascript')) return 'javascript';
      if (normalizedMime.includes('python')) return 'python';
      if (normalizedMime.includes('xml') || normalizedMime.includes('html')) return 'xml';
      if (normalizedMime.includes('markdown')) return 'markdown';
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
    
    // Try to detect JSON from content
    if (effectiveContent.trim().startsWith('{') || effectiveContent.trim().startsWith('[')) {
      try {
        JSON.parse(effectiveContent);
        return 'json';
      } catch {
        // Not JSON
      }
    }
    
    return 'text';
  }, [effectiveContent, normalizedMime, filename]);

  // Format JSON with proper indentation
  const formattedContent = useMemo(() => {
    if (contentType === 'json') {
      try {
        const parsed = JSON.parse(effectiveContent);
        return JSON.stringify(parsed, null, 2);
      } catch {
        return effectiveContent;
      }
    }
    return effectiveContent;
  }, [effectiveContent, contentType]);

  // Basic syntax highlighting via CSS classes
  const renderWithSyntax = () => {
    if (contentType === 'json') {
      return (
        <pre className="text-sm font-mono text-gray-800 whitespace-pre-wrap overflow-x-auto">
          <code className="language-json">{formattedContent}</code>
        </pre>
      );
    }

    if (contentType === 'javascript' || contentType === 'python' || contentType === 'xml' || contentType === 'yaml') {
      return (
        <pre className="text-sm font-mono text-gray-800 whitespace-pre-wrap overflow-x-auto">
          <code className={`language-${contentType}`}>{effectiveContent}</code>
        </pre>
      );
    }

    if (contentType === 'markdown') {
      return <MarkdownRenderer content={effectiveContent} />;
    }

    // Plain text
    return (
      <pre className="text-sm text-gray-800 whitespace-pre-wrap">
        {effectiveContent}
      </pre>
    );
  };

  return (
    <div className="prose prose-sm max-w-none prose-pre:bg-transparent prose-pre:p-0">
      {mediaNode ? mediaNode : effectiveContent ? renderWithSyntax() : (
        <p className="text-sm text-gray-400 italic">(No content)</p>
      )}
    </div>
  );
}
