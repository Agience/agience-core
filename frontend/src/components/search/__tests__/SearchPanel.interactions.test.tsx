import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { SearchPanel } from '../SearchPanel';
import type { Artifact } from '../../../context/workspace/workspace.types';

vi.mock('../../browser/AdvancedSearch', () => ({
  default: () => <div data-testid="advanced-search">advanced-search</div>,
}));

vi.mock('../../common/CardGrid', () => ({
  default: (props: {
    artifacts: Artifact[];
    selectedIds?: string[];
    selectable?: boolean;
    draggable?: boolean;
    onArtifactMouseDown?: (id: string, event: React.MouseEvent) => void;
    onOpenArtifact?: (artifact: Artifact) => void;
  }) => {
    const clickPlain = () => {
      props.onArtifactMouseDown?.(
        'root-1',
        { shiftKey: false, metaKey: false, ctrlKey: false } as React.MouseEvent,
      );
    };

    const clickCtrl = () => {
      props.onArtifactMouseDown?.(
        'root-2',
        { shiftKey: false, metaKey: false, ctrlKey: true } as React.MouseEvent,
      );
    };

    const dblClickOpen = () => {
      if (props.artifacts[0]) {
        props.onOpenArtifact?.(props.artifacts[0]);
      }
    };

    return (
      <div data-testid="mock-grid" data-selectable={String(props.selectable)} data-draggable={String(props.draggable)}>
        <div data-testid="selected-count">{props.selectedIds?.length ?? 0}</div>
        <button type="button" onClick={clickPlain}>plain</button>
        <button type="button" onClick={clickCtrl}>ctrl</button>
        <button type="button" onClick={dblClickOpen}>double</button>
        <div data-testid="artifact-count">{props.artifacts.length}</div>
      </div>
    );
  },
}));

vi.mock('../../common/CardList', () => ({
  default: (props: { artifacts: Artifact[]; selectable?: boolean; draggable?: boolean }) => (
    <div
      data-testid="mock-list"
      data-selectable={String(props.selectable)}
      data-draggable={String(props.draggable)}
    >
      {props.artifacts.length}
    </div>
  ),
}));

describe('SearchPanel interactions', () => {
  const artifacts: Artifact[] = [
    { id: 'v1', root_id: 'root-1', content: 'first', context: '{}', state: 'committed', collection_ids: [] } as Artifact,
    { id: 'v2', root_id: 'root-2', content: 'second', context: '{}', state: 'committed', collection_ids: [] } as Artifact,
  ];

  it('keeps the panel body blue by default', () => {
    const { container } = render(<SearchPanel artifacts={[]} />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain('bg-blue-50');
  });

  it('enables selectable + draggable artifact grid and does not open on plain click', () => {
    const onOpenArtifact = vi.fn();
    render(<SearchPanel artifacts={artifacts} onOpenArtifact={onOpenArtifact} />);

    const grid = screen.getByTestId('mock-grid');
    expect(grid.getAttribute('data-selectable')).toBe('true');
    expect(grid.getAttribute('data-draggable')).toBe('true');

    fireEvent.click(screen.getByRole('button', { name: 'plain' }));

    expect(screen.getByTestId('selected-count').textContent).toBe('1');
    expect(onOpenArtifact).not.toHaveBeenCalled();
  });

  it('opens artifact on double-click path', () => {
    const onOpenArtifact = vi.fn();
    render(<SearchPanel artifacts={artifacts} onOpenArtifact={onOpenArtifact} />);

    fireEvent.click(screen.getByRole('button', { name: 'double' }));

    expect(onOpenArtifact).toHaveBeenCalledTimes(1);
    expect(onOpenArtifact).toHaveBeenCalledWith(artifacts[0]);
  });

  it('renders only real artifacts (no collection matches in search response)', () => {
    const onCollectionSelect = vi.fn();

    render(
      <SearchPanel
        artifacts={artifacts}
        onCollectionSelect={onCollectionSelect}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Collection One' })).toBeNull();
    expect(screen.getByTestId('artifact-count').textContent).toBe('2');
    expect(onCollectionSelect).not.toHaveBeenCalled();
  });

  it('does not open artifact on ctrl-click to preserve multi-select behavior', () => {
    const onOpenArtifact = vi.fn();
    render(<SearchPanel artifacts={artifacts} onOpenArtifact={onOpenArtifact} />);

    fireEvent.click(screen.getByRole('button', { name: 'ctrl' }));

    expect(screen.getByTestId('selected-count').textContent).toBe('1');
    expect(onOpenArtifact).not.toHaveBeenCalled();
  });

  it('switches to list view from the result view toggle', () => {
    render(<SearchPanel artifacts={artifacts} />);

    fireEvent.click(screen.getByRole('button', { name: 'List view' }));

    expect(screen.getByTestId('mock-list')).toBeTruthy();
    expect(screen.getByTestId('mock-list').getAttribute('data-selectable')).toBe('true');
    expect(screen.getByTestId('mock-list').getAttribute('data-draggable')).toBe('true');
  });
});
