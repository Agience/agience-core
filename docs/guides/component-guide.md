# shadcn/ui Component Usage Guide

Status: **Reference**
Date: 2026-04-01

**Purpose**: Reference guide for UI components used in Agience — what's installed, what's active, and how to use each correctly.

> **Note on inputs and selects**: `Input`, `Label`, and `Select` shadcn components are **not installed**. Use plain HTML `<input>` / `<select>` with Tailwind classes instead. See [Best Practices](#best-practices) for the canonical pattern.

---

## Installed components

| Component | File | Status |
|---|---|---|
| `Button` | `ui/button.tsx` | ✅ Active |
| `IconButton` / `IconBadge` | `ui/icon-button.tsx` | ✅ Active (custom) |
| `Dialog` | `ui/dialog.tsx` | ✅ Active |
| `DropdownMenu` | `ui/dropdown-menu.tsx` | ✅ Active |
| `Sheet` | `ui/sheet.tsx` | ✅ Active |
| `Tabs` | `ui/tabs.tsx` | ✅ Active |
| `Command` | `ui/command.tsx` | ✅ Active |
| `ContextMenu` | `ui/context-menu.tsx` | ✅ Active |
| `Table` | `ui/table.tsx` | ✅ Active |
| `Skeleton` | `ui/skeleton.tsx` | ✅ Active |
| `Sonner` (toast) | `ui/sonner.tsx` | ✅ Active |
| `Tooltip` | `ui/tooltip.tsx` | ✅ Active |
| `Separator` | `ui/separator.tsx` | ✅ Active |
| `ScrollArea` | `ui/scroll-area.tsx` | ✅ Installed |
| `Accordion` | `ui/accordion.tsx` | ⚠️ Installed, not yet used in app |
| `Badge` | `ui/badge.tsx` | ⚠️ Installed, not yet used in app |
| `Popover` | `ui/popover.tsx` | ⚠️ Installed, not yet used in app |

---

## Table of contents

1. [Button](#button)
2. [IconButton / IconBadge](#iconbutton--iconbadge)
3. [Dialog](#dialog)
4. [DropdownMenu](#dropdownmenu)
5. [Sheet](#sheet)
6. [Tabs](#tabs)
7. [Command Palette](#command-palette)
8. [ContextMenu](#contextmenu)
9. [Table](#table)
10. [Skeleton](#skeleton)
11. [Sonner (Toast)](#sonner-toast)
12. [Tooltip](#tooltip)
13. [Separator](#separator)
14. [ScrollArea](#scrollarea)
15. [Installed but Unused](#installed-but-unused)
16. [Best Practices](#best-practices)

---

## Button

**Import**: `import { Button } from '@/components/ui/button'`

**Variants**: `default`, `destructive`, `outline`, `secondary`, `ghost`, `link`
**Sizes**: `default`, `sm`, `lg`, `icon`

**Usage**:
```tsx
// Primary action
<Button variant="default">Save</Button>

// Secondary / cancel
<Button variant="outline">Cancel</Button>

// Destructive
<Button variant="destructive">Delete</Button>

// Minimal
<Button variant="ghost" size="sm">Cancel</Button>

// Disabled
<Button disabled>Processing...</Button>
```

> **For icon-only buttons, use `IconButton` instead.** `Button size="icon"` is a fallback only.

**Examples in codebase**:
- `CardDetailModal.tsx`: Save/Close buttons
- `CommitBanner.tsx`: Commit action
- `CommitReviewDialog.tsx`: Confirm/cancel
- `SidebarEnhanced.tsx`: Edit/Add/Delete

---

## IconButton / IconBadge

**Import**: `import { IconButton, IconBadge } from '@/components/ui/icon-button'`

A **custom component** (not from shadcn). Square icon buttons with consistent sizing and a thin border. `IconBadge` is for non-interactive status indicators.

**IconButton props**:
- `size`: `'xs'` | `'sm'` | `'md'` | `'lg'` (default: `'md'`)
- `variant`: `'filled'` | `'ghost'` (default: `'ghost'`)
- `active`: `boolean` — applies filled style when true

```tsx
// Ghost (default)
<IconButton onClick={handleClose} aria-label="Close"><X /></IconButton>

// Filled — dark background, white icon
<IconButton variant="filled" aria-label="Settings"><Settings /></IconButton>

// Active/selected state
<IconButton active={isSelected} aria-label="Grid view"><Grid /></IconButton>

// Small
<IconButton size="sm" aria-label="Add"><Plus /></IconButton>
```

**IconBadge** — status indicator, not interactive:
```tsx
<IconBadge variant="success"><CheckCircle /></IconBadge>
<IconBadge variant="warning"><AlertTriangle /></IconBadge>
<IconBadge variant="error"><XCircle /></IconBadge>
```

**Examples in codebase**:
- `FloatingCardWindow.tsx`: Window controls
- `SidebarEnhanced.tsx`: Sidebar action buttons
- `MainHeader.tsx`: Header icon buttons

---

## Dialog

**Import**:
```tsx
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
```

**Usage**:
```tsx
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Edit Card</DialogTitle>
      <DialogDescription>Make changes to your card here.</DialogDescription>
    </DialogHeader>

    {/* Content */}

    <DialogFooter>
      <Button variant="outline" onClick={() => setIsOpen(false)}>Cancel</Button>
      <Button onClick={handleSave}>Save</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

**Features**: auto-focus, Escape to close, click-outside to close, accessible ARIA attributes.

**Examples in codebase**:
- `CardDetailModal.tsx`, `CollectionDetailModal.tsx`, `CollectionEditModal.tsx`
- `CollectionShareModal.tsx`, `WorkspaceDetailModal.tsx`, `WorkspaceStreamKeyModal.tsx`
- `WorkspaceInboundKeysModal.tsx`, `MCPServerModal.tsx`, `CommitReviewDialog.tsx`
- `SidebarEnhanced.tsx`, `HelpDialog.tsx`, `KeyboardShortcutsDialog.tsx`

---

## Wizard pattern (standard)

Agience uses a consistent **multi-step wizard** pattern for “set something up” flows (providers, connections, transcripts, imports).

### Where it appears

- Triggered from the owning surface (e.g., a Live Stream / StreamSource artifact action like **Transcript → Start**).
- Displayed as a `Dialog` so users don’t lose context.

### Structure

Inside `DialogContent`:

- Title: short verb phrase (e.g., “Start transcript”)
- Optional subtitle: what this applies to (e.g., stream name)
- Step indicator: “Step 1 of 3” (plain text)
- Step body: one focused choice/form per step
- Footer actions:
  - Left: `Back` (hidden/disabled on first step)
  - Right: `Next` / `Start` (primary)
  - Secondary: `Cancel` (outline)

### Components

Use only installed primitives:

- `Dialog` + `Button`
- Plain HTML `<input>` / `<select>` + Tailwind classes (shadcn `Input`/`Select` are not installed)
- Optional: `Tabs` for a two-mode choice (e.g., “Agience” vs “Use my AWS”)

### Data collection rules

- Keep step 1 **binary/simple** when possible (default path vs advanced path).
- Reuse a consistent “Connection picker” step:
  - list existing connections
  - button: “New connection”
  - after creation, return to the wizard with the new connection selected
- Never embed secrets into Operators. Credentials live in Connections; wizards should output references (IDs).

Implementation note:
- For provider-backed flows, define a small provider form schema with explicit **Required** vs **Optional** fields (see [external-auth.md](../features/external-auth.md)).

### Field rendering standard (forms)

Use a consistent visual language for all wizard forms:

- **Label**: short, human-readable (e.g., “Region”)
- **Required marker**: add “(required)” in plain text next to the label
- **Helper text** (optional): one sentence, example-driven (e.g., “Example: us-east-1”)
- **Placeholder**: use an example value, not a description

Validation and errors:

- Validate required fields before allowing `Next` / `Start`.
- Show one inline error per field (below the input), plus one summary line at the top if multiple fields are invalid.
- Never include secrets in error messages.

Safe display of saved connections:

- Display: `name` + provider + region (if applicable)
- Optional safe hint: account id / username returned from a test call
- Never display stored secrets after save; allow only “Test”, “Rotate”, “Delete”.

### Output rules (most flows)

- Create output artifact(s) in the **same workspace** as the initiating artifact.
- Store linkage in `context` via referenced IDs (e.g., source artifact id, agent artifact id, connection id).

---

## DropdownMenu

**Import**:
```tsx
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
```

> **Use `DropdownMenu`, not `Select`**, for sort/filter dropdowns. The `Select` component is not installed.

**Usage**:
```tsx
<DropdownMenu>
  <DropdownMenuTrigger asChild>
    <Button variant="ghost" size="sm">
      Sort <ChevronDown className="ml-1 h-4 w-4" />
    </Button>
  </DropdownMenuTrigger>
  <DropdownMenuContent align="start">
    <DropdownMenuItem onClick={() => onSortChange('title')}>Title</DropdownMenuItem>
    <DropdownMenuItem onClick={() => onSortChange('created')}>Created</DropdownMenuItem>
    <DropdownMenuSeparator />
    <DropdownMenuItem onClick={() => onSortChange('manual')}>Manual</DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

**Examples in codebase**:
- `FilterBar.tsx`: Sort and view mode dropdowns
- `SidebarEnhanced.tsx`: Item action menus
- `ContainerCardViewer.tsx`: Container actions
- `BrowserHeader.tsx`: View options

---

## Sheet

**Import**:
```tsx
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
```

A slide-in panel anchored to a screen edge. Sides: `'left'` | `'right'` (default) | `'top'` | `'bottom'`.

**Usage**:
```tsx
<Sheet open={isOpen} onOpenChange={setIsOpen}>
  <SheetContent side="right">
    <SheetHeader>
      <SheetTitle>Settings</SheetTitle>
    </SheetHeader>
    {/* Panel content */}
  </SheetContent>
</Sheet>
```

**Examples in codebase**:
- `SidebarEnhanced.tsx`: Slide-out detail/settings panel

---

## Tabs

**Import**:
```tsx
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
```

**Usage**:
```tsx
// Uncontrolled
<Tabs defaultValue="content">
  <TabsList>
    <TabsTrigger value="content">Content</TabsTrigger>
    <TabsTrigger value="context">Context</TabsTrigger>
  </TabsList>
  <TabsContent value="content">...</TabsContent>
  <TabsContent value="context">...</TabsContent>
</Tabs>

// Controlled
const [tab, setTab] = useState('content')
<Tabs value={tab} onValueChange={setTab}>...</Tabs>
```

**Examples in codebase**:
- `CardDetailModal.tsx`: Content / Context / Collections tabs
- `HelpDialog.tsx`: Help section tabs
- `BrowserHeader.tsx`: View mode tabs

---

## Command palette

**Import**:
```tsx
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
```

**Usage**:
```tsx
function CommandPalette() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen(o => !o)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Workspaces">
          {workspaces.map(ws => (
            <CommandItem key={ws.id} onSelect={() => handleSelect(ws.id)}>
              <NotebookPen className="mr-2 h-4 w-4" />
              {ws.name}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Collections">
          {/* ... */}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
```

**Features**: built-in fuzzy search, keyboard navigation (↑↓, Enter), groups and separators.

**Examples in codebase**:
- `CommandPalette.tsx`: Full implementation

---

## ContextMenu

**Import**:
```tsx
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
```

**Usage**:
```tsx
<ContextMenu>
  <ContextMenuTrigger>
    <div className="border rounded p-4">Right-click me</div>
  </ContextMenuTrigger>
  <ContextMenuContent>
    <ContextMenuItem onClick={handleOpen}>
      <Eye className="mr-2 h-4 w-4" /> Open
    </ContextMenuItem>
    <ContextMenuSeparator />
    <ContextMenuItem onClick={handleDelete} className="text-red-600">
      <Trash className="mr-2 h-4 w-4" /> Delete
    </ContextMenuItem>
  </ContextMenuContent>
</ContextMenu>
```

**Examples in codebase**:
- `CardGridItem.tsx` / `CardListItem.tsx`: State-aware artifact context menus

---

## Table

**Import**:
```tsx
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
```

**Usage**:
```tsx
<div className="rounded-md border">
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead>Name</TableHead>
        <TableHead className="text-right">Actions</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {data.map(item => (
        <TableRow key={item.id}>
          <TableCell className="font-medium">{item.name}</TableCell>
          <TableCell className="text-right">
            <Button variant="ghost" size="sm">Edit</Button>
          </TableCell>
        </TableRow>
      ))}
      {data.length === 0 && (
        <TableRow>
          <TableCell colSpan={2} className="text-center py-8">No data</TableCell>
        </TableRow>
      )}
    </TableBody>
  </Table>
</div>
```

**Examples in codebase**:
- `CollectionDetailModal.tsx`: Shares table
- `CollectionShareModal.tsx`: Collection sharing table (legacy share-link/grant transition)

---

## Skeleton

**Import**: `import { Skeleton } from '@/components/ui/skeleton'`

Prefer the shared wrappers in `CardSkeleton.tsx` over raw `Skeleton` elements.

**Usage**:
```tsx
// Raw
<Skeleton className="h-4 w-full" />
<Skeleton className="h-4 w-3/4" />

// Shared wrappers (preferred)
import { CardSkeleton, SidebarItemSkeleton } from '@/components/common/CardSkeleton'
<CardSkeleton count={6} />
<SidebarItemSkeleton count={3} />
```

**Loading state pattern**:
```tsx
{isLoading
  ? <CardSkeleton count={6} />
  : cards.map(card => <CardGridItem key={card.id} card={card} />)
}
```

**Examples in codebase**:
- `CardSkeleton.tsx`: Reusable skeleton components
- `CardDetailModal.tsx`: Loading collection list

---

## Sonner (Toast)

**Import**: `import { toast } from 'sonner'`

`<Toaster />` is already rendered at app root in `App.tsx`.

**Usage**:
```tsx
toast.success('Card saved')
toast.error('Failed to save card')
toast.info('Processing...')
toast.warning('This action cannot be undone')

// With action
toast('Card deleted', {
  description: 'This cannot be undone.',
  action: { label: 'Undo', onClick: handleUndo },
})
```

**Examples in codebase**:
- `WorkspaceProvider.tsx`: Success/error notifications
- `CollectionShareModal.tsx`: Copy confirmation (legacy sharing UI; direction is grant-token sharing)

---

## Tooltip

**Import**:
```tsx
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
```

`TooltipProvider` is already mounted at `ThreeColumnLayout.tsx` — no need to add it locally.

**Usage**:
```tsx
<Tooltip>
  <TooltipTrigger asChild>
    <IconButton aria-label="Settings"><Settings /></IconButton>
  </TooltipTrigger>
  <TooltipContent>Settings</TooltipContent>
</Tooltip>
```

**Examples in codebase**:
- `ThreeColumnLayout.tsx`: `TooltipProvider` mounted at layout root

---

## Separator

**Import**: `import { Separator } from '@/components/ui/separator'`

**Usage**:
```tsx
// Horizontal (default)
<Separator />

// Vertical
<Separator orientation="vertical" className="h-4" />
```

**Examples in codebase**:
- `CommitReviewDialog.tsx`, `HelpDialog.tsx`, `KeyboardShortcutsDialog.tsx`

---

## ScrollArea

**Import**: `import { ScrollArea } from '@/components/ui/scroll-area'`

Styled scrollable region with a custom scrollbar. Use instead of raw `overflow-auto` when consistent scrollbar styling matters.

**Usage**:
```tsx
<ScrollArea className="h-72 rounded-md border">
  <div className="p-4">
    {items.map(item => <div key={item.id}>{item.name}</div>)}
  </div>
</ScrollArea>

// Horizontal
<ScrollArea className="w-full whitespace-nowrap">
  <div className="flex gap-2">
    {items.map(item => <Chip key={item.id} />)}
  </div>
  <ScrollBar orientation="horizontal" />
</ScrollArea>
```

---

## Installed but unused

These are installed and ready to use. Reach for them before building custom alternatives.

### Accordion
```tsx
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'

<Accordion type="multiple" defaultValue={["section1"]}>
  <AccordionItem value="section1">
    <AccordionTrigger>Section 1</AccordionTrigger>
    <AccordionContent>Content here</AccordionContent>
  </AccordionItem>
</Accordion>
```

### Badge
```tsx
import { Badge } from '@/components/ui/badge'

<Badge variant="default">New</Badge>
<Badge variant="secondary">42</Badge>
<Badge variant="destructive">Error</Badge>
<Badge variant="outline">Synced</Badge>
```

### Popover
```tsx
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

<Popover>
  <PopoverTrigger asChild>
    <IconButton aria-label="Help"><HelpCircle /></IconButton>
  </PopoverTrigger>
  <PopoverContent className="w-80">Help text here</PopoverContent>
</Popover>
```

---

## Best practices

### 1. Icon buttons
Always use `IconButton`, not `Button size="icon"`:
```tsx
// Correct
<IconButton onClick={handleClose} aria-label="Close"><X /></IconButton>

// Avoid
<Button variant="ghost" size="icon"><X /></Button>
```

### 2. Accessibility
- Every `IconButton` must have `aria-label`
- Use `Tooltip` to surface the label visually when there’s no adjacent text
- Maintain heading hierarchy (`h1` → `h2` → `h3`)

### 3. Loading states
Use `CardSkeleton` / `SidebarItemSkeleton`, not raw `<Skeleton>`:
```tsx
{isLoading
  ? <CardSkeleton count={6} />
  : cards.map(card => <CardGridItem key={card.id} card={card} />)
}
```

### 4. Dropdowns vs Select
`Select` is not installed. Use `DropdownMenu` for all dropdown needs:
```tsx
// Correct
<DropdownMenu>...</DropdownMenu>
```

### 5. Plain inputs
`Input` and `Label` are not installed. Use plain HTML with Tailwind:
```tsx
<label htmlFor="name" className="text-sm font-medium text-gray-700">Name</label>
<input
  id="name"
  type="text"
  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-gray-400"
  value={name}
  onChange={e => setName(e.target.value)}
/>
```

### 6. Performance
Lazy-load heavy components:
```tsx
const CommandPalette = lazy(() => import('./CommandPalette'))

<Suspense fallback={null}>
  <CommandPalette />
</Suspense>
```

Memoize filtered lists:
```tsx
const filtered = useMemo(
  () => cards.filter(c => c.state === activeFilter),
  [cards, activeFilter]
)
```

### 7. Keyboard shortcuts
Platform-aware modifiers:
```tsx
const isMac = navigator.platform.includes('Mac')
const shortcut = isMac ? '⌘K' : 'Ctrl+K'
```

---

## Common Patterns

### Modal with Tabs
```tsx
<Dialog open={open} onOpenChange={setOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Edit Item</DialogTitle>
    </DialogHeader>
    <Tabs defaultValue="general">
      <TabsList>
        <TabsTrigger value="general">General</TabsTrigger>
        <TabsTrigger value="advanced">Advanced</TabsTrigger>
      </TabsList>
      <TabsContent value="general">{/* Form */}</TabsContent>
      <TabsContent value="advanced">{/* Advanced */}</TabsContent>
    </Tabs>
    <DialogFooter>
      <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
      <Button onClick={handleSave}>Save</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

### Table with Actions
```tsx
<Table>
  <TableHeader>
    <TableRow>
      <TableHead>Name</TableHead>
      <TableHead className="text-right">Actions</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    {items.map(item => (
      <TableRow key={item.id}>
        <TableCell>{item.name}</TableCell>
        <TableCell className="text-right">
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => handleEdit(item)}>Edit</Button>
            <Button variant="ghost" size="sm" className="text-red-600" onClick={() => handleDelete(item)}>Delete</Button>
          </div>
        </TableCell>
      </TableRow>
    ))}
  </TableBody>
</Table>
```

---

## Troubleshooting

### Styles not applying
Check Tailwind config includes app source:
```js
// tailwind.config.js
content: ["./src/**/*.{js,jsx,ts,tsx}"]
```

### Components not resolving
Verify `@/` alias in `tsconfig.json`:
```json
{ "compilerOptions": { "paths": { "@/*": ["./src/*"] } } }
```

### Toasts not showing
Confirm `<Toaster />` is rendered at app root in `App.tsx`.

---

## Resources

- [shadcn/ui Documentation](https://ui.shadcn.com/)
- [Radix UI Documentation](https://www.radix-ui.com/)
- [Tailwind CSS Documentation](https://tailwindcss.com/)
- [Lucide Icons](https://lucide.dev/)
