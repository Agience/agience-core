import { describe, it, expect } from 'vitest';

import type { PaletteState } from '../palette.types';
import { applyTransformSpec, buildTransformSpec, computeTransformHash, getTransformFromArtifact, makeTransformArtifactContext } from '../orderSpec';
import type { Artifact } from '../../workspace/workspace.types';
import type { PanelKey } from '../palette.types';

describe('transformSpec', () => {
  const fakeArtifact = (id: string): Artifact => ({
    id,
    context: '{}',
    content: '',
    state: 'draft',
    collection_ids: [],
  }) as unknown as Artifact;

  const baseState: PaletteState = {
    panelData: {
      input: { artifacts: [fakeArtifact('c1')], text: 'hello' },
      resources: { artifacts: [fakeArtifact('c2')], resources: [{ server: 's', uri: 'u' }] },
      context: { artifacts: [fakeArtifact('cx')] },
      prompts: { artifacts: [fakeArtifact('c3')], selectedId: 'p1' },
      instructions: { artifacts: [], text: 'do thing' },
      tools: { tools: ['t1'] },
      knowledge: { artifacts: [fakeArtifact('c4')] },
      options: { config: { x: 1 } },
      agent: { config: {} },
      targets: {
        collections: [{ id: 'col1', name: 'C' }] as unknown as PaletteState['panelData']['targets']['collections'],
      },
      output: {
        artifacts: [{ id: 'out1', content: 'x', context: '{}' }] as unknown as PaletteState['panelData']['output']['artifacts'],
      },
    },
    panelStatus: {} as PaletteState['panelStatus'],
    updatePanelStatus: (() => {}) as PaletteState['updatePanelStatus'],
  };

  it('builds a v1 transform spec and computes a stable hash', () => {
    const spec = buildTransformSpec({ state: baseState, breakpoints: new Set<PanelKey>(['agent']), title: 'My Transform' });
    expect(spec.kind).toBe('agience.transform');
    expect(spec.version).toBe(1);
    expect(spec.title).toBe('My Transform');
    expect(spec.panelData.input.text).toBe('hello');

    const h1 = computeTransformHash(spec);
    const h2 = computeTransformHash(spec);
    expect(h1).toBe(h2);
  });

  it('applyTransformSpec overwrites config panels and resets derived output/context', () => {
    const spec = buildTransformSpec({ state: baseState, breakpoints: new Set(), title: 'My Transform' });
    const next = applyTransformSpec(baseState, spec);

    expect(next.panelData.input.text).toBe('hello');
    expect(next.panelData.context.artifacts).toEqual([]);
    expect(next.panelData.output.artifacts).toEqual([]);
  });

  it('roundtrips from a Transform artifact context', () => {
    const spec = buildTransformSpec({ state: baseState, breakpoints: new Set(), title: 'My Transform' });
    const ctx = makeTransformArtifactContext({
      title: 'My Transform',
      kind: 'palette',
      subtype: 'research',
      run: { type: 'palette-run' },
      spec,
    });

    const artifact = {
      id: 'transform1',
      context: JSON.stringify(ctx),
      content: 'x',
      state: 'draft',
      collection_ids: [],
    } as unknown as Artifact;

    const parsed = getTransformFromArtifact(artifact);
    expect(parsed?.spec.kind).toBe('agience.transform');
    expect(parsed?.title).toBe('My Transform');
    expect(parsed?.kind).toBe('palette');
    expect(parsed?.subtype).toBe('research');
    expect(parsed?.run?.type).toBe('palette-run');
  });

  it('accepts legacy order artifacts without metadata', () => {
    const spec = buildTransformSpec({ state: baseState, breakpoints: new Set(), title: 'Legacy Order' });
    const artifact = {
      id: 'legacy-order',
      context: JSON.stringify({ title: 'Legacy Order', order: { spec } }),
      content: 'x',
      state: 'draft',
      collection_ids: [],
    } as unknown as Artifact;

    const parsed = getTransformFromArtifact(artifact);
    expect(parsed?.title).toBe('Legacy Order');
    expect(parsed?.kind).toBeUndefined();
    expect(parsed?.subtype).toBeUndefined();
    expect(parsed?.run).toBeUndefined();
  });
});
