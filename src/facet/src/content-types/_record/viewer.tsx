import { useEffect, useMemo, useState } from 'react';
import {
  BellRing,
  Building2,
  FileText,
  HardDrive,
  KeyRound,
  Pencil,
  Save,
  ShieldCheck,
  Wallet,
  X,
  type LucideIcon,
} from 'lucide-react';
import type { Artifact } from '@/context/workspace/workspace.types';
import { useWorkspace } from '@/hooks/useWorkspace';
import { useArtifactContent } from '@/hooks/useArtifactContent';
import type { ViewMode, ViewState } from '@/registry/content-types';
import { cn } from '@/lib/utils';
import { safeParseArtifactContext, stringifyArtifactContext } from '@/utils/artifactContext';

type FieldDescriptor = {
  path: string;
  label?: string;
  editable?: boolean;
  editor?: 'text' | 'number' | 'url' | 'textarea' | 'boolean';
};

type RecordDefinition = {
  label: string;
  icon?: LucideIcon;
  iconClass?: string;
  titlePath?: string;
  subtitlePath?: string;
  badgePath?: string;
  hero?: {
    valuePath: string;
    valueClassName?: string;
    secondaryPath?: string;
    secondaryClassName?: string;
    containerClassName?: string;
  };
  fields?: FieldDescriptor[];
  collections?: FieldDescriptor[];
  objects?: FieldDescriptor[];
};

type ScalarEditorProps = {
  id: string;
  descriptor: FieldDescriptor;
  value: unknown;
  onChange: (value: unknown) => void;
};

const DEFAULT_BADGE_CLASSES: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  recorded: 'bg-blue-100 text-blue-800',
  grace: 'bg-amber-100 text-amber-800',
  warning: 'bg-amber-100 text-amber-800',
  revoked: 'bg-rose-100 text-rose-800',
  expired: 'bg-slate-200 text-slate-700',
  pending: 'bg-sky-100 text-sky-800',
  suspended: 'bg-orange-100 text-orange-800',
  'needs-license': 'bg-rose-100 text-rose-800',
  draft: 'bg-slate-100 text-slate-700',
  sent: 'bg-blue-100 text-blue-800',
  paid: 'bg-emerald-100 text-emerald-800',
  void: 'bg-rose-100 text-rose-800',
  info: 'bg-sky-100 text-sky-800',
};

const RECORD_DEFINITIONS: Record<string, RecordDefinition> = {
  'application/vnd.agience.organization+json': {
    label: 'Organization',
    icon: Building2,
    iconClass: 'text-cyan-600',
    titlePath: 'identity.display_name',
    subtitlePath: 'identity.legal_name',
    fields: [
      { path: 'identity.entity_kind', label: 'Entity Kind' },
      { path: 'identity.jurisdiction', label: 'Jurisdiction', editable: true },
      { path: 'identity.website_uri', label: 'Website', editable: true, editor: 'url' },
      { path: 'licensing.employee_count', label: 'Employees', editable: true, editor: 'number' },
      { path: 'licensing.annual_gross_revenue_usd', label: 'Annual Gross Revenue (USD)', editable: true, editor: 'number' },
    ],
    collections: [
      { path: 'relationships.affiliate_organization_ids', label: 'Affiliates', editable: true },
    ],
    objects: [
      { path: 'identity', label: 'Identity' },
      { path: 'licensing.packaging', label: 'Packaging' },
    ],
  },
  'application/vnd.agience.account+json': {
    label: 'Account',
    icon: Wallet,
    iconClass: 'text-amber-500',
    titlePath: 'provider',
    subtitlePath: 'account_type',
    hero: {
      valuePath: 'balance',
      secondaryPath: 'currency',
      valueClassName: 'text-2xl font-bold text-amber-700 font-mono',
      secondaryClassName: 'text-sm text-amber-600',
      containerClassName: 'bg-amber-50 border-amber-100',
    },
    fields: [
      { path: 'account_type', label: 'Account Type' },
      { path: 'currency', label: 'Currency' },
      { path: 'provider', label: 'Provider' },
      { path: 'last_synced_at', label: 'Last Synced' },
    ],
  },
  'application/vnd.agience.license+json': {
    label: 'License',
    icon: ShieldCheck,
    iconClass: 'text-emerald-500',
    titlePath: 'title',
    subtitlePath: 'license_id',
    badgePath: 'state',
    fields: [
      { path: 'account_id', label: 'Account' },
      { path: 'policy_id', label: 'Policy' },
      { path: 'control_class', label: 'Control Class' },
      { path: 'product_surface', label: 'Product Surface' },
      { path: 'expires_at', label: 'Expires' },
      { path: 'artifact_status', label: 'Artifact Status' },
    ],
    collections: [
      { path: 'runtime_roles', label: 'Runtime Roles' },
      { path: 'distribution_profiles', label: 'Profiles' },
      { path: 'branding_scope', label: 'Branding Scope' },
      { path: 'entitlements', label: 'Entitlements' },
    ],
    objects: [
      { path: 'limits', label: 'Limits' },
      { path: 'features', label: 'Features' },
      { path: 'operator', label: 'Operator' },
    ],
  },
  'application/vnd.agience.entitlement+json': {
    label: 'Entitlement',
    icon: KeyRound,
    iconClass: 'text-blue-500',
    titlePath: 'title',
    subtitlePath: 'entitlement_id',
    badgePath: 'state',
    fields: [
      { path: 'account_id', label: 'Account' },
      { path: 'policy_id', label: 'Policy' },
      { path: 'profile', label: 'Profile' },
      { path: 'issued_at', label: 'Issued' },
      { path: 'expires_at', label: 'Expires' },
      { path: 'downstream_customer', label: 'Downstream Customer' },
    ],
    collections: [
      { path: 'runtime_roles', label: 'Runtime Roles' },
      { path: 'branding_scope', label: 'Branding Scope' },
      { path: 'required_entitlements', label: 'Required Entitlements' },
      { path: 'operator.authorized_entitlements', label: 'Authorized Entitlements' },
    ],
    objects: [{ path: 'operator', label: 'Operator' }],
  },
  'application/vnd.agience.license-installation+json': {
    label: 'Installation',
    icon: HardDrive,
    iconClass: 'text-violet-500',
    titlePath: 'title',
    subtitlePath: 'install_id',
    badgePath: 'compliance_state',
    fields: [
      { path: 'license_id', label: 'License' },
      { path: 'instance_id', label: 'Instance ID' },
      { path: 'device_id', label: 'Device ID' },
      { path: 'profile', label: 'Profile' },
      { path: 'lease_expires_at', label: 'Lease Expires' },
      { path: 'last_validated_at', label: 'Last Validated' },
      { path: 'last_reviewed_at', label: 'Last Reviewed' },
    ],
  },
  'application/vnd.agience.license-usage+json': {
    label: 'Usage Snapshot',
    icon: FileText,
    iconClass: 'text-orange-500',
    titlePath: 'title',
    subtitlePath: 'usage_id',
    badgePath: 'state',
    fields: [
      { path: 'account_id', label: 'Account' },
      { path: 'license_id', label: 'License' },
      { path: 'captured_at', label: 'Captured At' },
      { path: 'reporting_period', label: 'Reporting Period' },
      { path: 'source_artifact_id', label: 'Source Artifact' },
    ],
    objects: [
      { path: 'usage', label: 'Usage' },
      { path: 'allowances', label: 'Allowances' },
      { path: 'overages', label: 'Overages' },
    ],
  },
  'application/vnd.agience.license-event+json': {
    label: 'Licensing Event',
    icon: BellRing,
    iconClass: 'text-rose-500',
    titlePath: 'title',
    subtitlePath: 'event_type',
    badgePath: 'severity',
    fields: [
      { path: 'event_type', label: 'Event Type' },
      { path: 'account_id', label: 'Account' },
      { path: 'license_id', label: 'License' },
      { path: 'reason', label: 'Reason' },
      { path: 'created_at', label: 'Created At' },
    ],
    objects: [{ path: 'details', label: 'Details' }],
  },
};

function toLabel(path: string): string {
  const segments = path.split('.');
  const segment = segments[segments.length - 1] ?? path;
  return segment.replace(/_/g, ' ').replace(/\b\w/g, (char: string) => char.toUpperCase());
}

function getValue(input: unknown, path: string): unknown {
  if (!path) return input;
  return path.split('.').reduce<unknown>((current, key) => {
    if (current && typeof current === 'object' && key in (current as Record<string, unknown>)) {
      return (current as Record<string, unknown>)[key];
    }
    return undefined;
  }, input);
}

function setValue(input: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const keys = path.split('.');
  const nextRoot: Record<string, unknown> = { ...input };
  let cursor: Record<string, unknown> = nextRoot;

  keys.forEach((key, index) => {
    const isLeaf = index === keys.length - 1;
    if (isLeaf) {
      cursor[key] = value;
      return;
    }

    const current = cursor[key];
    const next = current && typeof current === 'object' && !Array.isArray(current)
      ? { ...(current as Record<string, unknown>) }
      : {};
    cursor[key] = next;
    cursor = next;
  });

  return nextRoot;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function normalizeScalarValue(descriptor: FieldDescriptor, raw: string, currentValue: unknown): unknown {
  const editor = descriptor.editor ?? 'text';
  if (editor === 'number') {
    if (raw.trim() === '') return '';
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : currentValue;
  }
  if (editor === 'boolean') {
    return raw === 'true';
  }
  return raw;
}

function renderScalarEditor({ id, descriptor, value, onChange }: ScalarEditorProps) {
  const editor = descriptor.editor ?? 'text';
  const normalizedValue = value === null || value === undefined ? '' : String(value);

  if (editor === 'textarea') {
    return (
      <textarea
        id={id}
        value={normalizedValue}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-[88px] rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
      />
    );
  }

  if (editor === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-sm text-gray-800">
        <input
          id={id}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => onChange(event.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
        />
        Enabled
      </label>
    );
  }

  return (
    <input
      id={id}
      type={editor}
      value={normalizedValue}
      onChange={(event) => onChange(normalizeScalarValue(descriptor, event.target.value, value))}
      className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
    />
  );
}

function renderCollection(label: string, values: unknown) {
  if (!Array.isArray(values) || values.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500">{label}</div>
      <div className="flex flex-wrap gap-2">
        {values.map((value) => (
          <span
            key={String(value)}
            className="rounded-full bg-gray-100 px-2 py-1 text-[11px] font-medium text-gray-700"
          >
            {String(value)}
          </span>
        ))}
      </div>
    </div>
  );
}

function renderCollectionEditor({
  id,
  label,
  values,
  onChange,
}: {
  id: string;
  label: string;
  values: unknown;
  onChange: (value: string[]) => void;
}) {
  const normalizedValues = Array.isArray(values) ? values.map((value) => String(value)).join('\n') : '';
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {label}
      </label>
      <textarea
        id={id}
        value={normalizedValues}
        onChange={(event) => {
          const nextValues = event.target.value
            .split(/\r?\n|,/) 
            .map((value) => value.trim())
            .filter(Boolean);
          onChange(nextValues);
        }}
        className="min-h-[96px] rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
      />
      <div className="text-xs text-gray-500">One value per line.</div>
    </div>
  );
}

function renderObjectBlock(label: string, value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-gray-200 bg-gray-50 p-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500">{label}</div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs leading-5 text-gray-700">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function fallbackDefinition(mime: string | undefined): RecordDefinition {
  return {
    label: mime ?? 'Record',
    icon: FileText,
    iconClass: 'text-slate-500',
    titlePath: 'title',
    subtitlePath: 'content_type',
    fields: [{ path: 'content_type', label: 'Content Type' }],
  };
}

export default function RecordViewer({
  artifact,
}: {
  artifact: Artifact;
  mode?: ViewMode;
  state?: ViewState;
}) {
  const { artifacts, updateArtifact } = useWorkspace();
  const { content: resolvedContent } = useArtifactContent(artifact);
  const ctx = useMemo<Record<string, unknown>>(() => safeParseArtifactContext(artifact.context), [artifact.context]);
  const [draftContext, setDraftContext] = useState<Record<string, unknown>>(ctx);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const mime = typeof ctx.content_type === 'string' ? ctx.content_type : undefined;
  const definition = mime ? (RECORD_DEFINITIONS[mime] ?? fallbackDefinition(mime)) : fallbackDefinition(undefined);
  const isWorkspaceArtifact = useMemo(
    () => artifacts.some((workspaceArtifact) => String(workspaceArtifact.id) === String(artifact.id)),
    [artifacts, artifact.id]
  );
  const activeContext = isEditing ? draftContext : ctx;
  const Icon = definition.icon ?? FileText;
  const title = formatValue(getValue(activeContext, definition.titlePath ?? 'title'));
  const subtitle = definition.subtitlePath ? formatValue(getValue(activeContext, definition.subtitlePath)) : '—';
  const badgeValue = definition.badgePath ? formatValue(getValue(activeContext, definition.badgePath)) : '';
  const badgeRaw = definition.badgePath ? String(getValue(activeContext, definition.badgePath) ?? '').toLowerCase() : '';
  const badgeClass = DEFAULT_BADGE_CLASSES[badgeRaw] ?? 'bg-slate-100 text-slate-700';
  const heroValue = definition.hero ? getValue(activeContext, definition.hero.valuePath) : undefined;
  const heroSecondary = definition.hero?.secondaryPath ? getValue(activeContext, definition.hero.secondaryPath) : undefined;
  const fields: FieldDescriptor[] = definition.fields?.length
    ? definition.fields
    : Object.keys(activeContext)
        .filter((key) => !['title', 'content_type', 'type'].includes(key))
        .map((key): FieldDescriptor => ({ path: key }));
  const editableFields = fields.filter((field) => field.editable);
  const editableCollections = (definition.collections ?? []).filter((field) => field.editable);

  useEffect(() => {
    setDraftContext(ctx);
    setIsEditing(false);
  }, [ctx]);

  const handleFieldChange = (path: string, value: unknown) => {
    setDraftContext((current) => setValue(current, path, value));
  };

  const handleSave = async () => {
    if (!artifact.id) return;
    setIsSaving(true);
    try {
      await updateArtifact({
        id: String(artifact.id),
        context: stringifyArtifactContext(draftContext),
      });
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setDraftContext(ctx);
    setIsEditing(false);
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto bg-white p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-xl bg-gray-50 p-2 ring-1 ring-gray-200">
          <Icon size={16} className={definition.iconClass ?? 'text-slate-500'} />
        </div>
        <div className="min-w-0 flex-1">
          {isEditing && definition.titlePath ? (
            <div className="flex flex-col gap-2">
              <div>
                <label htmlFor="record-title" className="sr-only">Title</label>
                {renderScalarEditor({
                  id: 'record-title',
                  descriptor: { path: definition.titlePath, label: 'Title', editable: true },
                  value: getValue(draftContext, definition.titlePath),
                  onChange: (value) => handleFieldChange(definition.titlePath!, value),
                })}
              </div>
              {definition.subtitlePath && (
                <div>
                  <label htmlFor="record-subtitle" className="sr-only">Subtitle</label>
                  {renderScalarEditor({
                    id: 'record-subtitle',
                    descriptor: { path: definition.subtitlePath, label: 'Subtitle', editable: true },
                    value: getValue(draftContext, definition.subtitlePath),
                    onChange: (value) => handleFieldChange(definition.subtitlePath!, value),
                  })}
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="truncate text-sm font-semibold text-gray-900">
                {title !== '—' ? title : definition.label}
              </div>
              {subtitle !== '—' && <div className="mt-1 text-xs text-gray-500">{subtitle}</div>}
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {badgeValue && badgeValue !== '—' && (
            <span className={cn('rounded-full px-2 py-1 text-[11px] font-medium capitalize', badgeClass)}>
              {badgeValue}
            </span>
          )}
          {isWorkspaceArtifact && (editableFields.length > 0 || editableCollections.length > 0 || Boolean(definition.titlePath)) && (
            isEditing ? (
              <>
                <button
                  type="button"
                  onClick={() => void handleSave()}
                  disabled={isSaving}
                  className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
                >
                  <Save size={14} />
                  Save
                </button>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-200"
                >
                  <X size={14} />
                  Cancel
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                className="inline-flex items-center gap-1 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 transition hover:bg-blue-100"
              >
                <Pencil size={14} />
                Edit
              </button>
            )
          )}
        </div>
      </div>

      {heroValue !== undefined && heroValue !== null && heroValue !== '' && (
        <div
          className={cn(
            'flex items-baseline gap-2 rounded-lg border px-3 py-2',
            definition.hero?.containerClassName ?? 'bg-slate-50 border-slate-100'
          )}
        >
          <span className={definition.hero?.valueClassName ?? 'text-2xl font-bold text-slate-700 font-mono'}>
            {String(heroValue)}
          </span>
          {heroSecondary !== undefined && heroSecondary !== null && heroSecondary !== '' && (
            <span className={definition.hero?.secondaryClassName ?? 'text-sm text-slate-500'}>
              {String(heroSecondary)}
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 rounded-xl border border-gray-200 bg-gray-50 p-3">
        {fields.map((field) => (
          <div key={field.path} className="flex flex-col gap-1">
            <label htmlFor={`record-field-${field.path}`} className="text-[11px] uppercase tracking-wide text-gray-500">
              {field.label ?? toLabel(field.path)}
            </label>
            {isEditing && field.editable ? (
              renderScalarEditor({
                id: `record-field-${field.path}`,
                descriptor: field,
                value: getValue(draftContext, field.path),
                onChange: (value) => handleFieldChange(field.path, value),
              })
            ) : (
              <div className="text-sm text-gray-800">{formatValue(getValue(activeContext, field.path))}</div>
            )}
          </div>
        ))}
      </div>

      {(definition.collections ?? []).map((field) => (
        isEditing && field.editable
          ? (
            <div key={field.path}>
              {renderCollectionEditor({
                id: `record-collection-${field.path}`,
                label: field.label ?? toLabel(field.path),
                values: getValue(draftContext, field.path),
                onChange: (value) => handleFieldChange(field.path, value),
              })}
            </div>
          )
          : <div key={field.path}>{renderCollection(field.label ?? toLabel(field.path), getValue(activeContext, field.path))}</div>
      ))}
      {(definition.objects ?? []).map((field) => (
        <div key={field.path}>
          {renderObjectBlock(field.label ?? toLabel(field.path), getValue(activeContext, field.path))}
        </div>
      ))}

      {isEditing && (definition.objects ?? []).length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Nested object blocks remain read-only in the generic editor for now. Scalar fields and lists are editable here; structured JSON stays explicit until we add schema-driven editors.
        </div>
      )}

      {resolvedContent && (
        <div className="rounded-xl border border-gray-200 bg-white p-3">
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-500">Summary</div>
          <div className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-700">{resolvedContent}</div>
        </div>
      )}
    </div>
  );
}