import { useMemo } from 'react';

type FormValue = Record<string, unknown>;

export type DynamicFieldType = 'text' | 'textarea' | 'select' | 'boolean' | 'string-list';

export interface DynamicFieldOption {
  label: string;
  value: string;
}

export interface DynamicCardFormField {
  path: string;
  label: string;
  type: DynamicFieldType;
  placeholder?: string;
  helpText?: string;
  rows?: number;
  options?: DynamicFieldOption[];
}

interface DynamicCardFormProps {
  value: FormValue;
  fields: DynamicCardFormField[];
  onChange: (next: FormValue) => void;
}

function getPathValue(source: Record<string, unknown>, path: string): unknown {
  const parts = path.split('.').filter(Boolean);
  let current: unknown = source;
  for (const part of parts) {
    if (!current || typeof current !== 'object' || Array.isArray(current)) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function setPathValue(source: FormValue, path: string, value: unknown): FormValue {
  const parts = path.split('.').filter(Boolean);
  if (parts.length === 0) return source;

  const next: FormValue = { ...source };
  let cursor: Record<string, unknown> = next;

  for (let i = 0; i < parts.length - 1; i += 1) {
    const key = parts[i];
    const existing = cursor[key];
    const child = existing && typeof existing === 'object' && !Array.isArray(existing)
      ? { ...(existing as Record<string, unknown>) }
      : {};
    cursor[key] = child;
    cursor = child;
  }

  cursor[parts[parts.length - 1]] = value;
  return next;
}

export function DynamicCardForm({ value, fields, onChange }: DynamicCardFormProps) {
  const normalized = useMemo(() => (value && typeof value === 'object' ? value : {}), [value]);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {fields.map((field) => {
        const raw = getPathValue(normalized, field.path);
        const textValue = typeof raw === 'string' ? raw : '';
        const isWide = field.type === 'textarea' || field.type === 'string-list';

        return (
          <label
            key={field.path}
            className={`flex flex-col gap-1.5 text-sm text-slate-700 ${isWide ? 'md:col-span-2' : ''}`}
          >
            <span className="font-medium">{field.label}</span>

            {field.type === 'text' && (
              <input
                value={textValue}
                onChange={(event) => onChange(setPathValue(normalized, field.path, event.target.value))}
                className="rounded border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                placeholder={field.placeholder}
              />
            )}

            {field.type === 'textarea' && (
              <textarea
                value={textValue}
                onChange={(event) => onChange(setPathValue(normalized, field.path, event.target.value))}
                rows={field.rows ?? 4}
                className="rounded border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                placeholder={field.placeholder}
              />
            )}

            {field.type === 'select' && (
              <select
                value={textValue}
                onChange={(event) => onChange(setPathValue(normalized, field.path, event.target.value))}
                className="rounded border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
              >
                <option value="">Select…</option>
                {(field.options ?? []).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            )}

            {field.type === 'boolean' && (
              <div className="flex items-center gap-2 rounded border border-slate-200 px-3 py-2">
                <input
                  type="checkbox"
                  checked={Boolean(raw)}
                  onChange={(event) => onChange(setPathValue(normalized, field.path, event.target.checked))}
                />
                <span className="text-sm text-slate-700">Enabled</span>
              </div>
            )}

            {field.type === 'string-list' && (
              <textarea
                value={Array.isArray(raw) ? raw.map(String).join('\n') : ''}
                onChange={(event) => {
                  const list = event.target.value
                    .split(/\r?\n/)
                    .map((item) => item.trim())
                    .filter(Boolean);
                  onChange(setPathValue(normalized, field.path, list));
                }}
                rows={field.rows ?? 4}
                className="rounded border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
                placeholder={field.placeholder}
              />
            )}

            {field.helpText ? <span className="text-xs text-slate-500">{field.helpText}</span> : null}
          </label>
        );
      })}
    </div>
  );
}
