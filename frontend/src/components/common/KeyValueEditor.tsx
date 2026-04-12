// src/components/shared/KeyValueEditor.tsx
import { useState } from 'react';
import { X, Download } from 'lucide-react';
import { getArtifactContentUrl } from '../../api/workspaces';
import { useWorkspaces } from '../../hooks/useWorkspaces';
import { toast } from 'sonner';

export type JSONValue =
  | string
  | number
  | boolean
  | null
  | JSONValue[]
  | { [key: string]: JSONValue };

export type JSONObject = { [key: string]: JSONValue };

const STANDARD = [
  { key: 'description',  label: 'Description',   kind: 'textarea' as const, maxLength: undefined },
  { key: 'title',        label: 'Title',         kind: 'title'    as const, maxLength: 140 },
  { key: 'content_type', label: 'Content Type',  kind: 'text'     as const, maxLength: undefined },
  { key: 'tags',         label: 'Tags',          kind: 'tags'     as const, maxLength: undefined },
] as const;

// System-managed fields that should be readonly in the UI
const READONLY_SYSTEM_FIELDS = new Set([
  'access',          // Access control: "private" (signed URLs) or "public" (direct access)
  'content_source',  // Content source: "agience-content", "external-url", etc.
  'uri',             // Public URI (only for access="public" with external content)
  'size',            // File size in bytes
  'mime',            // MIME type
  'filename',        // Original filename
  'upload',          // Upload status/progress (transient, removed after completion)
]);

type PrimitiveKind = 'string' | 'number' | 'boolean' | 'null' | 'json';

type CustomRow = {
  id: string;
  key: string;
  kind: PrimitiveKind;
  value: string | number | boolean | null;
  error?: string;
};

function uniqueId(prefix = 'row') {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

function isPrimitive(v: unknown): v is string | number | boolean | null {
  return v === null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean';
}

function inferKindForExisting(v: JSONValue): PrimitiveKind {
  if (v === null) return 'null';
  if (typeof v === 'number') return 'number';
  if (typeof v === 'boolean') return 'boolean';
  if (typeof v === 'string') {
    const s = v.trim();
    if ((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']'))) {
      try { JSON.parse(s); return 'json'; } catch {
        // nothing
      }
    }
    return 'string';
  }
  return 'json';
}

function ensureTyped(kind: PrimitiveKind, raw: string | number | boolean | null) {
  if (kind === 'number') return typeof raw === 'number' ? raw : (raw === '' ? '' : Number(raw));
  if (kind === 'boolean') return typeof raw === 'boolean' ? raw : raw === 'true';
  if (kind === 'null') return null;
  return typeof raw === 'string' ? raw : String(raw ?? '');
}

function DownloadButton({ artifactId, filename }: { artifactId: string; filename: string }) {
  const { activeWorkspace } = useWorkspaces();
  const [loading, setLoading] = useState(false);

  const handleDownload = async () => {
    if (!activeWorkspace) {
      toast.error('No workspace selected');
      return;
    }

    setLoading(true);
    try {
      const { url, expires_in } = await getArtifactContentUrl(activeWorkspace.id, artifactId);
      
      // Open in new tab to trigger download
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.target = '_blank';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      if (expires_in == null) {
        toast.success('Download started (public URL)');
      } else {
        const expiryMin = Math.floor(expires_in / 60);
        toast.success(`Download started (URL expires in ${expiryMin}m)`);
      }
    } catch (error) {
      console.error('Download error:', error);
      toast.error('Failed to generate download URL');
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleDownload}
      disabled={loading}
      className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      <Download size={14} />
      {loading ? 'Getting URL...' : 'Download'}
    </button>
  );
}

function Header({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center justify-between mb-1">
      <label className="text-xs text-gray-700">{label}</label>
      <button
        type="button"
        aria-label={`Remove ${label}`}
        onClick={onRemove}
        className="p-1 text-gray-500 hover:text-gray-800"
      >
        <X size={14} />
      </button>
    </div>
  );
}

function StandardField({
  name,
  label,
  kind,
  maxLength,
  value,
  onChange,
  onRemove,
}: {
  name: typeof STANDARD[number]['key'];
  label: string;
  kind: 'textarea' | 'text' | 'title' | 'tags';
  maxLength?: number;
  value: JSONValue | undefined;
  onChange: (next: JSONValue) => void;
  onRemove: () => void;
}) {
  if (kind === 'textarea') {
    return (
      <div className="space-y-1">
        <Header label={label} onRemove={onRemove} />
        <textarea
          className="w-full border border-gray-300 rounded p-2 text-sm min-h-[80px]"
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={name}
        />
      </div>
    );
  }

  if (kind === 'title') {
    const v = typeof value === 'string' ? value : '';
    return (
      <div className="space-y-1">
        <Header label={label} onRemove={onRemove} />
        <input
          type="text"
          className="w-full border border-gray-300 rounded p-2 text-sm"
          value={v}
          maxLength={maxLength}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Title"
        />
        <div className="flex items-center justify-end text-[10px] text-gray-500">
          <span>{v.length}/{maxLength}</span>
        </div>
      </div>
    );
  }

  if (kind === 'tags') {
    const tags = Array.isArray(value) && value.every((t) => typeof t === 'string') ? (value as string[]) : [];
    return (
      <div className="space-y-1">
        <Header label={label} onRemove={onRemove} />
        <TagsInput tags={tags} onChange={(next) => onChange(next)} />
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <Header label={label} onRemove={onRemove} />
      <input
        type="text"
        className="w-full border border-gray-300 rounded p-2 text-sm"
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={label}
      />
    </div>
  );
}

function TagsInput({
  tags,
  onChange,
}: {
  tags: string[];
  onChange: (next: string[]) => void;
}) {
  const [input, setInput] = useState('');
  const add = (t: string) => {
    const tag = t.trim();
    if (!tag) return;
    if (tags.includes(tag)) return;
    onChange([...tags, tag]);
    setInput('');
  };
  const remove = (t: string) => onChange(tags.filter((x) => x !== t));
  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-2">
        {tags.map((t) => (
          <span key={t} className="inline-flex items-center gap-1 text-xs bg-white border border-gray-300 rounded-full px-2 py-1">
            {t}
            <button type="button" className="text-gray-500 hover:text-gray-800" onClick={() => remove(t)}>×</button>
          </span>
        ))}
      </div>
      <input
        className="w-full border border-gray-300 rounded p-2 text-sm"
        placeholder="Type a tag and press Enter or comma"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            add(input);
          }
          if (e.key === 'Backspace' && input === '' && tags.length) {
            onChange(tags.slice(0, -1));
          }
        }}
        onBlur={() => add(input)}
      />
    </div>
  );
}

export default function KeyValueEditor({
  value,
  onChange,
  artifactId,
  filename,
}: {
  value: JSONObject;
  onChange: (next: JSONObject) => void;
  artifactId?: string;
  filename?: string;
}) {
  // Keep local state authoritative to avoid wiping empty custom rows
  const [obj, setObj] = useState<JSONObject>(value);

  const toCustomRows = (o: JSONObject): CustomRow[] =>
    Object.entries(o)
      .filter(([k]) => !STANDARD.some((s) => s.key === k) && !READONLY_SYSTEM_FIELDS.has(k))
      .map(([k, v]) => {
        const kind = inferKindForExisting(v);
        const vv =
          kind === 'json'
            ? typeof v === 'string'
              ? v
              : JSON.stringify(v)
            : (isPrimitive(v) ? v : '');
        return { id: uniqueId('row'), key: k, kind, value: ensureTyped(kind, vv) as string | number | boolean | null };
      });

  const [rows, setRows] = useState<CustomRow[]>(() => toCustomRows(value));

  const commit = (nextObj: JSONObject, nextRows = rows) => {
    const rebuilt: JSONObject = {};
    for (const r of nextRows) {
      const k = r.key.trim();
      if (!k) continue; // keep empty-row local only
      if (r.kind === 'json') {
        const s = String(r.value ?? '').trim();
        if (s) {
          try { JSON.parse(s); rebuilt[k] = s; } catch {
            // nothing
          }
        } else {
          rebuilt[k] = '';
        }
      } else if (r.kind === 'boolean') {
        rebuilt[k] = Boolean(r.value);
      } else if (r.kind === 'number') {
        rebuilt[k] = typeof r.value === 'number' ? r.value : Number(r.value);
      } else if (r.kind === 'null') {
        rebuilt[k] = null;
      } else {
        rebuilt[k] = typeof r.value === 'string' ? r.value : String(r.value ?? '');
      }
    }
    const merged: JSONObject = { ...rebuilt };
    // Preserve standard fields
    for (const { key } of STANDARD) {
      if (key in nextObj) merged[key] = nextObj[key];
    }
    // Preserve readonly system fields
    for (const key of READONLY_SYSTEM_FIELDS) {
      if (key in nextObj) merged[key] = nextObj[key];
    }
    setObj(merged);
    onChange(merged);
  };

  // standard helpers
  const hasStandard = (k: typeof STANDARD[number]['key']) => Object.prototype.hasOwnProperty.call(obj, k);
  const setStandard = (k: typeof STANDARD[number]['key'], v: JSONValue) => {
    const next = { ...obj, [k]: v };
    setObj(next);
    commit(next);
  };
  const removeStandard = (k: typeof STANDARD[number]['key']) => {
    if (!hasStandard(k)) return;
    const next = { ...obj };
    delete next[k];
    setObj(next);
    commit(next);
  };

  // custom ops
  const addCustom = () => {
    // Do not commit yet; empty key would be dropped by commit + parent echo
    setRows(prev => [
      ...prev,
      { id: uniqueId(), key: '', kind: 'string', value: '' }
    ]);
  };
  const removeCustom = (id: string) => {
    setRows(prev => {
      const next = prev.filter(r => r.id !== id);
      commit(obj, next);
      return next;
    });
  };
  const updateCustomKey = (id: string, newKey: string) => {
    setRows(prev => {
      const next = prev.map(r => (r.id === id ? { ...r, key: newKey } : r));
      commit(obj, next);
      return next;
    });
  };
  const updateCustomKind = (id: string, kind: PrimitiveKind) => {
    setRows(prev => {
      const next = prev.map(r => (r.id === id ? { ...r, kind, value: ensureTyped(kind, r.value) } : r));
      commit(obj, next);
      return next;
    });
  };
  const updateCustomValue = (id: string, raw: string) => {
    setRows(prev => {
      const row = prev.find(r => r.id === id);
      if (!row) return prev;
      if (row.kind === 'json') {
        let err = '';
        if (raw.trim()) {
          try { JSON.parse(raw); } catch { err = 'Invalid JSON'; }
        }
        const next = prev.map(r => (r.id === id ? { ...r, value: raw, error: err } : r));
        commit(obj, next);
        return next;
      }
      const typed =
        row.kind === 'number' ? (raw.trim() === '' ? '' : Number(raw)) :
        row.kind === 'boolean' ? (raw === 'true') :
        row.kind === 'null' ? null :
        raw;
      const next = prev.map(r => (r.id === id ? { ...r, value: typed } : r));
      commit(obj, next);
      return next;
    });
  };

  const missingStandards = STANDARD.filter(({ key }) => !hasStandard(key));

  // Extract readonly system fields
  const systemFields = Object.entries(obj).filter(([k]) => READONLY_SYSTEM_FIELDS.has(k));
  
  // Check if this artifact has a downloadable file (has 'content_source' field) and we have artifactId
  const hasFile = artifactId && obj.content_source === 'agience-content';

  return (
    <div className="space-y-4">
      {/* Readonly System Metadata Section */}
      {systemFields.length > 0 && (
        <div className="space-y-2 pb-3 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              System Metadata (Read-only)
            </div>
            {hasFile && (
              <DownloadButton 
                artifactId={artifactId!} 
                filename={filename || obj.filename as string || 'download'} 
              />
            )}
          </div>
          {systemFields.map(([key, val]) => {
            const strVal = typeof val === 'object' ? JSON.stringify(val) : String(val);
            
            return (
              <div key={key} className="grid grid-cols-3 gap-2 text-sm">
                <div className="font-mono text-gray-600">{key}</div>
                <div className="col-span-2 font-mono text-gray-800 bg-gray-50 px-2 py-1 rounded text-xs overflow-x-auto whitespace-nowrap">
                  {strVal}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {STANDARD.filter(({ key }) => hasStandard(key)).length > 0 && (
        <div className="space-y-3">
          {STANDARD.filter(({ key }) => hasStandard(key)).map(({ key, label, kind, maxLength }) => (
            <StandardField
              key={key}
              name={key}
              label={label}
              kind={kind}
              maxLength={maxLength}
              value={obj[key]}
              onChange={(v) => setStandard(key, v)}
              onRemove={() => removeStandard(key)}
            />
          ))}
        </div>
      )}

      {missingStandards.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {missingStandards.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className="px-2 py-1 text-xs border rounded hover:bg-gray-50"
              onClick={() => {
                const init =
                  key === 'description' ? '' :
                  key === 'title' ? '' :
                  key === 'content_type' ? 'text/plain' :
                  key === 'tags' ? [] : '';
                setStandard(key, init as JSONValue);
              }}
            >
              Add {label}
            </button>
          ))}
        </div>
      )}

      <div className="border-t pt-3 space-y-2">
        {rows.map((r) => (
          <div key={r.id} className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-xs text-gray-700">Custom field</label>
              <button
                type="button"
                aria-label="Remove custom field"
                onClick={() => removeCustom(r.id)}
                className="p-1 text-gray-500 hover:text-gray-800"
              >
                <X size={14} />
              </button>
            </div>

            <div className="grid grid-cols-6 gap-2">
              <input
                className="col-span-2 border border-gray-300 rounded p-2 text-sm"
                placeholder="key"
                value={r.key}
                onChange={(e) => updateCustomKey(r.id, e.target.value)}
              />
              <select
                className="col-span-1 border border-gray-300 rounded p-2 text-sm"
                value={r.kind}
                onChange={(e) => updateCustomKind(r.id, e.target.value as PrimitiveKind)}
              >
                <option value="string">string</option>
                <option value="number">number</option>
                <option value="boolean">boolean</option>
                <option value="null">null</option>
                <option value="json">json</option>
              </select>

              {r.kind === 'boolean' ? (
                <select
                  className="col-span-2 border border-gray-300 rounded p-2 text-sm"
                  value={String(r.value)}
                  onChange={(e) => updateCustomValue(r.id, e.target.value)}
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : r.kind === 'null' ? (
                <input
                  className="col-span-2 border border-gray-200 rounded p-2 text-sm bg-gray-50"
                  value="null"
                  readOnly
                />
              ) : r.kind === 'number' ? (
                <input
                  type="number"
                  className="col-span-2 border border-gray-300 rounded p-2 text-sm"
                  value={typeof r.value === 'number' ? r.value : ''}
                  onChange={(e) => updateCustomValue(r.id, e.target.value)}
                />
              ) : r.kind === 'json' ? (
                <input
                  className={`col-span-2 border rounded p-2 text-sm ${r.error ? 'border-red-500' : 'border-gray-300'}`}
                  placeholder='e.g. {"a":1} or ["x","y"]'
                  value={typeof r.value === 'string' ? r.value : String(r.value ?? '')}
                  onChange={(e) => updateCustomValue(r.id, e.target.value)}
                />
              ) : (
                <input
                  className="col-span-2 border border-gray-300 rounded p-2 text-sm"
                  value={typeof r.value === 'string' ? r.value : String(r.value ?? '')}
                  onChange={(e) => updateCustomValue(r.id, e.target.value)}
                />
              )}
            </div>

            {r.kind === 'json' && r.error && (
              <div className="text-[11px] text-red-600">{r.error}</div>
            )}
          </div>
        ))}

        <div className="pt-1">
          <button
            type="button"
            onClick={addCustom}
            className="px-2 py-1 text-sm border rounded hover:bg-gray-50"
          >
            Add field
          </button>
        </div>
      </div>
    </div>
  );
}
