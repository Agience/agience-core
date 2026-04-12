import { describe, expect, it } from 'vitest';
import { getAgienceDragPayload, getDroppedArtifactIds, AGIENCE_DRAG_CONTENT_TYPE } from '../agienceDrag';

function makeDT(data: Record<string, string>, types?: string[]) {
  return {
    types: types ?? Object.keys(data),
    getData: (t: string) => data[t] ?? '',
  } as unknown as DataTransfer;
}

describe('agienceDrag', () => {
  it('parses unified artifacts payload', () => {
    const dt = makeDT({
      [AGIENCE_DRAG_CONTENT_TYPE]: JSON.stringify({ kind: 'artifacts', ids: ['a', 'b'] }),
    });
    expect(getDroppedArtifactIds(dt)).toEqual(['a', 'b']);
  });

  it('parses JSON artifact payload', () => {
    const dt = makeDT({
      'application/json': JSON.stringify({ ids: ['c1'] }),
    });
    expect(getDroppedArtifactIds(dt)).toEqual(['c1']);
  });

  it('returns tool payload when present', () => {
    const dt = makeDT({
      [AGIENCE_DRAG_CONTENT_TYPE]: JSON.stringify({ kind: 'tool', server: 'agience-core', tool_name: 'extract_information' }),
    });
    expect(getAgienceDragPayload(dt)).toEqual({ kind: 'tool', server: 'agience-core', tool_name: 'extract_information' });
  });
});
