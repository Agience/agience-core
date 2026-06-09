import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import EditableCardViewer from './EditableCardViewer';

vi.mock('@/components/preview/CardEditor', () => ({
  CardEditor: ({ artifactId }: { artifactId: string }) => <div data-testid="card-editor">editor-{artifactId}</div>,
}));

vi.mock('@/content-types/_shared/RenderedCardViewer', () => ({
  default: () => <div data-testid="rendered-card-viewer">rendered-card-viewer</div>,
}));

describe('EditableCardViewer', () => {
  it('renders the read-only viewer in view state', () => {
    render(
      <EditableCardViewer
        artifact={{
          id: 'artifact-1',
          context: JSON.stringify({ title: 'Test Artifact', content_type: 'text/plain' }),
          content: 'hello',
          state: 'committed' as const,
        }}
        state="view"
      />,
    );

    expect(screen.getByTestId('rendered-card-viewer')).toBeInTheDocument();
    expect(screen.queryByTestId('card-editor')).not.toBeInTheDocument();
  });

  it('renders the editor only in edit state', () => {
    render(
      <EditableCardViewer
        artifact={{
          id: 'artifact-1',
          context: JSON.stringify({ title: 'Test Artifact', content_type: 'text/plain' }),
          content: 'hello',
          state: 'committed' as const,
        }}
        state="edit"
      />,
    );

    expect(screen.getByTestId('card-editor')).toHaveTextContent('editor-artifact-1');
    expect(screen.queryByTestId('rendered-card-viewer')).not.toBeInTheDocument();
  });
});