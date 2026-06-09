/**
 * Conformance tests for the content-types plugin's inheritance merge.
 *
 * FACET's `deepMerge` MUST behave identically to MANTLE's `_deep_merge`
 * (src/mantle/services/types_service.py) so the build-time viewer registry and
 * the runtime type resolver agree on how `inherits` resolves. The documented
 * MANTLE contract: "objects recurse, child wins; lists replaced by child."
 * These cases pin FACET to that exact contract.
 */
import { describe, it, expect } from 'vitest';
import { deepMerge } from '../content-types-plugin';

describe('deepMerge — MANTLE _deep_merge parity', () => {
  it('recurses into nested plain objects, child wins per-key', () => {
    const parent = { a: 1, b: { x: 1, y: 2 } };
    const child = { b: { y: 3, z: 4 } };
    expect(deepMerge(parent, child)).toEqual({ a: 1, b: { x: 1, y: 3, z: 4 } });
  });

  it('child scalar overrides parent scalar', () => {
    expect(deepMerge({ label: 'A' }, { label: 'B' })).toEqual({ label: 'B' });
  });

  it('replaces arrays entirely (no element merge)', () => {
    expect(deepMerge({ modes: ['a', 'b', 'c'] }, { modes: ['z'] })).toEqual({ modes: ['z'] });
  });

  it('child non-object replaces a parent object', () => {
    expect(deepMerge({ a: { x: 1 } }, { a: 5 })).toEqual({ a: 5 });
  });

  it('child object replaces a parent scalar', () => {
    expect(deepMerge({ a: 5 }, { a: { x: 1 } })).toEqual({ a: { x: 1 } });
  });

  it('null child overrides (e.g. viewer: null is an intentional override)', () => {
    expect(deepMerge({ viewer: 'json' }, { viewer: null })).toEqual({ viewer: null });
  });

  it('keeps parent-only keys and adds child-only keys', () => {
    expect(deepMerge({ a: 1, keep: true }, { b: 2 })).toEqual({ a: 1, keep: true, b: 2 });
  });

  it('multi-level nesting recurses all the way down', () => {
    const parent = { ui: { theme: { color: 'red', size: 1 } } };
    const child = { ui: { theme: { size: 2 } } };
    expect(deepMerge(parent, child)).toEqual({ ui: { theme: { color: 'red', size: 2 } } });
  });

  it('is order-sensitive: applying parents then child matches inheritance order', () => {
    // grandparent -> parent -> child, applied left to right
    const grandparent = { a: 1, b: 1, c: 1 };
    const parent = { b: 2, c: 2 };
    const child = { c: 3 };
    const merged = deepMerge(deepMerge(grandparent, parent), child);
    expect(merged).toEqual({ a: 1, b: 2, c: 3 });
  });
});
