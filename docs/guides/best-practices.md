# Development Best Practices

Status: **Reference**
Date: 2026-03-31

Patterns and conventions for contributors working on the Agience codebase. Covers testing, React state management, performance, error handling, component design, and TypeScript.

---

## Testing

- Ship tests with every feature, behavioral change, or regression fix. A PR without coverage updates is incomplete.
- When fixing a regression, write the failing test first — before applying the patch. This prevents the bug from resurfacing.
- Keep fixtures realistic: use production-representative field names, timestamps, and IDs so assertions catch schema drift and serialization issues.
- Mock external systems (ArangoDB, OpenSearch, S3) using dependency overrides or `MagicMock`. Tests must never write to real infrastructure.
- Assert on domain outcomes (artifact states, search metadata, HTTP status codes) rather than internal implementation details.
- When patching services, stub full objects instead of bare booleans to avoid false confidence.
- Run `pytest tests` locally before pushing. Keep the suite free of skips unless tracked with an issue reference.
- Pair tests with linting: run `ruff check .` in `backend/` and `npm run lint` in `frontend/`. CI blocks merges when lints fail.

---

## React & state management

### Use context for shared state

```typescript
// WorkspaceContext is the single source of truth
const { selectedCardIds, cards, updateCard } = useWorkspace();
```

**Why**: Duplicating state in local components causes state drift and synchronization bugs. Read from context; don't shadow it.

---

### Avoid arrays and objects in useEffect dependencies

```typescript
// ❌ BAD: Array reference changes every render → infinite loop
useEffect(() => {
  setState(propsArray);
}, [propsArray]);

// ✅ GOOD: Depend on a stable primitive
useEffect(() => {
  setState(propsArray);
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [open]);
```

**Why**: Arrays and objects get new references on every render, triggering effects infinitely. Symptom: browser tab freezes, "Maximum update depth exceeded" error.

---

### Always wrap JSON.parse()

```typescript
// ✅ GOOD: Defensive parsing
const ctx = useMemo(() => {
  if (!card) return {};
  try {
    return typeof card.context === 'string'
      ? JSON.parse(card.context)
      : (card.context || {});
  } catch (error) {
    console.warn('Failed to parse context:', card.id, error);
    return {};
  }
}, [card]);
```

**Why**: External data (API, DB) may be malformed. Graceful degradation is better than a crash that leaves users with a blank screen.

---

### Hooks must come before early returns

```typescript
// ❌ BAD: Hook called after early return — never executed
function Component({ card }) {
  if (!card) return null;
  const ctx = useMemo(() => parse(card), [card]);
}

// ✅ GOOD: All hooks before early returns
function Component({ card }) {
  const ctx = useMemo(() => {
    if (!card) return {};
    return parse(card);
  }, [card]);

  if (!card) return null;
}
```

**Why**: React requires hooks to be called in the same order every render.

---

## Performance

### useMemo for expensive operations

```typescript
const filteredCollections = useMemo(() => {
  if (!searchQuery) return collections;
  return collections.filter(c =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  );
}, [collections, searchQuery]);
```

Use `useMemo` for: filtering/sorting large arrays (>50 items), complex calculations, JSON parsing, date formatting.

Do not use it for: simple operations (<10 items), primitive comparisons, already-fast operations.

---

### Set for O(1) lookups

```typescript
// ✅ O(1) lookups
const [selected, setSelected] = useState<Set<string>>(new Set());
const isSelected = selected.has(id);

// ❌ O(n) lookups
const [selected, setSelected] = useState<string[]>([]);
const isSelected = selected.includes(id);
```

Use `Set` for: multi-select with frequent lookups, uniqueness checks, large collections (>20 items). Use `Array` for ordered lists, small collections, or when array methods are needed.

---

## Error handling

### Graceful degradation

```typescript
// ✅ Sensible fallback
const title = ctx.title || ctx.filename || 'Untitled';
```

Always provide fallback values for fields that may be missing from external data.

---

### Log warnings, not errors

```typescript
// ✅ Warn and continue
try {
  return JSON.parse(data);
} catch (error) {
  console.warn('Parse failed:', error);
  return {};
}
```

Most parsing and rendering errors are recoverable. Throwing crashes the component tree; warn and return a safe default instead.

---

### Toast for user feedback

```typescript
try {
  await createCollection(name);
  toast.success(`Created "${name}"`);
} catch (error) {
  console.error('API error:', error);
  toast.error('Failed to create collection');
}
```

Toast for: API failures, successful user-triggered operations.
Do not toast for: background operations, inline validation errors, silent fallbacks.

---

## Component design

### Composition over prop drilling

```typescript
// ✅ Clean composition
<ThreeColumnLayout
  leftPanel={<Sidebar />}
  centerPanel={<Browser />}
  rightPanel={<PreviewPane />}
/>
```

Deeply nested prop chains are hard to test and modify. Use context or composition to avoid passing props through multiple levels.

---

### Single responsibility

Each component should do one thing. If a component exceeds ~300 lines, consider splitting it.

---

### Consistent interfaces

```typescript
interface CardItemProps {
  card: Card;
  isSelected: boolean;
  onSelect: (id: string) => void;
}

<CardGridItem {...props} />
<CardListItem {...props} />
```

Grid and list variants that accept the same props can swap implementations without re-rendering parent state.

---

## TypeScript patterns

### Explicit return types for complex functions

```typescript
// ✅
function parseContext(card: Card): Record<string, unknown> {
  try {
    return JSON.parse(card.context);
  } catch {
    return {};
  }
}
```

---

### Avoid `any`

```typescript
// ✅ Use unknown + narrow with a type guard
let ctx: { title?: string; [key: string]: unknown } = {};

// ❌ Defeats TypeScript
let ctx: any = {};
```

`any` is acceptable for: third-party libraries without types, temporary stubs during refactoring. Prefer `unknown` for external data.

---

### Optional chaining

```typescript
// ✅
const title = card?.context?.title || 'Untitled';

// ❌ Verbose null guards
const title = card && card.context && card.context.title ? card.context.title : 'Untitled';
```

---

## Debugging strategies

### Infinite loops

**Symptoms**: browser tab freezes, console floods, "Maximum update depth exceeded".

```typescript
// 1. Add logging in the effect to see how often it fires
useEffect(() => {
  console.log('Effect running', { deps });
}, [deps]);

// 2. Use React DevTools Profiler to find the rapidly re-rendering component

// 3. Isolate deps one at a time
useEffect(() => { ... }, []); // empty first
useEffect(() => { ... }, [dep1]); // add one at a time
```

Common causes: arrays/objects in dependency arrays, `setState` in an effect without a guard, parent re-render triggering child effect.

---

### JSON parse errors

**Symptoms**: "Unexpected token" error, component crash on specific artifacts.

```typescript
try {
  return JSON.parse(card.context);
} catch (error) {
  console.error('Parse failed for card:', card.id, error);
  console.log('Context value:', card.context);
  return {};
}
```

Common causes: plain text in a JSON field, malformed JSON, already-parsed object passed to `JSON.parse`.

---

### Stale state

**Symptoms**: UI doesn't reflect changes, console shows correct data.

```typescript
// Log state on each render
console.log('Rendering with state:', selectedCardIds);

// Watch for state changes
useEffect(() => {
  console.log('State changed:', selectedCardIds);
}, [selectedCardIds]);
```

Common causes: mutating state directly instead of replacing it, multiple sources of truth, batched async state updates.

---

## Common anti-patterns

| Anti-pattern | Fix |
|---|---|
| **Prop drilling** (>2 levels) | Use Context or composition |
| **God components** (500+ lines) | Split into focused sub-components |
| **Magic numbers** (`width: 360`) | Named constants (`PREVIEW_PANEL_WIDTH = 360`) |
| **Silent failures** (`catch { }`) | Log or notify the user |
| **Premature optimization** | Profile first, then optimize the measured bottleneck |

---

## Resources

- [Local Development](../getting-started/local-development.md)
- [Component Guide](./component-guide.md)
- [Architecture Overview](../architecture/layered-architecture.md)
- [React Hooks Rules](https://react.dev/reference/rules/rules-of-hooks)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)
