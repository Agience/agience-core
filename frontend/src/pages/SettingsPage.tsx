/**
 * pages/SettingsPage.tsx
 *
 * Platform admin settings page. Gated by the platform:admin role
 * (merged from platform:operator + platform:admin on 2026-04-06).
 * Manages all platform configuration stored in the platform_settings
 * ArangoDB collection via the /platform/* endpoints.
 */

import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useAdmin } from '@/hooks/useAdmin';
import { useAuth } from '@/hooks/useAuth';
import {
  listUsers,
  grantPlatformAdmin,
  revokePlatformAdmin,
  listSeedCollections,
  getPlatformSettings,
  updatePlatformSettings,
} from '@/api/platform';
import type { PlatformUser, SeedCollection } from '@/api/platform';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
//  Shared settings form helpers
// ---------------------------------------------------------------------------

type SettingField = {
  key: string
  label: string
  type: 'text' | 'password' | 'email' | 'number' | 'toggle'
  placeholder?: string
  help?: string
  is_secret?: boolean
}

function SettingsForm({
  fields,
  values,
  onChange,
  onSave,
  saving,
  testButton,
}: {
  fields: SettingField[]
  values: Record<string, string>
  onChange: (key: string, value: string) => void
  onSave: () => void
  saving: boolean
  testButton?: React.ReactNode
}) {
  return (
    <div className="space-y-4">
      {fields.map((f) => (
        <div key={f.key} className="space-y-1.5">
          <label className="block text-sm font-medium text-foreground">{f.label}</label>
          {f.type === 'toggle' ? (
            <button
              onClick={() => onChange(f.key, values[f.key] === 'true' ? 'false' : 'true')}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                values[f.key] === 'true' ? 'bg-indigo-600' : 'bg-gray-300'
              }`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                values[f.key] === 'true' ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          ) : (
            <input
              type={f.type === 'password' ? 'password' : f.type}
              value={values[f.key] || ''}
              onChange={(e) => onChange(f.key, e.target.value)}
              placeholder={f.placeholder}
              className="w-full px-3 py-2 border border-input rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring bg-background"
              autoComplete="off"
            />
          )}
          {f.help && <p className="text-xs text-muted-foreground">{f.help}</p>}
        </div>
      ))}
      <div className="flex items-center gap-3 pt-2">
        <Button onClick={onSave} disabled={saving} size="sm">
          {saving ? 'Saving...' : 'Save changes'}
        </Button>
        {testButton}
      </div>
    </div>
  );
}

// Shared props for all settings tabs that read/write platform_settings
type SettingsTabProps = {
  values: Record<string, string>
  onChange: (key: string, value: string) => void
  loaded: boolean
}

// ---------------------------------------------------------------------------
//  Tab: Users (existing)
// ---------------------------------------------------------------------------

function UsersTab() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [loading, setLoading] = useState(true);

  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listUsers();
      setUsers(data);
    } catch {
      toast.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  const handleToggleAdmin = async (userId: string, isAdmin: boolean) => {
    try {
      if (isAdmin) {
        await revokePlatformAdmin(userId);
        toast.success('Admin access revoked');
      } else {
        await grantPlatformAdmin(userId);
        toast.success('Admin access granted');
      }
      loadUsers();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to update admin status');
    }
  };

  if (loading) return <p className="text-sm text-muted-foreground p-4">Loading users...</p>;

  return (
    <div className="space-y-2">
      {users.map((u) => (
        <div key={u.id} className="flex items-center justify-between rounded-lg border px-4 py-3">
          <div className="flex items-center gap-3">
            {u.picture ? (
              <img src={u.picture} alt="" className="h-8 w-8 rounded-full" />
            ) : (
              <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
                {u.name?.[0]?.toUpperCase() || '?'}
              </div>
            )}
            <div>
              <p className="text-sm font-medium">{u.name}</p>
              <p className="text-xs text-muted-foreground">{u.email}</p>
            </div>
            {u.is_platform_admin && <Badge variant="secondary">Admin</Badge>}
          </div>
          {u.id !== currentUser?.id && (
            <Button variant={u.is_platform_admin ? 'outline' : 'default'} size="sm" onClick={() => handleToggleAdmin(u.id, u.is_platform_admin)}>
              {u.is_platform_admin ? 'Revoke Admin' : 'Grant Admin'}
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
//  Tab: Seed Content (existing)
// ---------------------------------------------------------------------------

function SeedContentTab() {
  const [collections, setCollections] = useState<SeedCollection[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await listSeedCollections();
        setCollections(data);
      } catch { toast.error('Failed to load seed collections'); }
      finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <p className="text-sm text-muted-foreground p-4">Loading collections...</p>;

  return (
    <div className="space-y-2">
      {collections.map((col) => (
        <div key={col.id} className="rounded-lg border px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">{col.name}</p>
              <p className="text-xs text-muted-foreground">{col.description}</p>
            </div>
            <Badge variant="outline">{col.artifact_count} artifacts</Badge>
          </div>
        </div>
      ))}
      {collections.length === 0 && <p className="text-sm text-muted-foreground">No platform collections found.</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
//  Tab: Authentication
// ---------------------------------------------------------------------------

function AuthenticationTab({ values, onChange, loaded }: SettingsTabProps) {
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const settings = Object.entries(values)
        .filter(([k]) => k.startsWith('auth.'))
        .map(([key, value]) => ({
          key, value,
          is_secret: key.includes('secret') || key.includes('password'),
        }));
      const result = await updatePlatformSettings(settings);
      toast.success(`${result.updated} settings saved`);
    } catch { toast.error('Failed to save settings'); }
    finally { setSaving(false); }
  };

  if (!loaded) return <p className="text-sm text-muted-foreground p-4">Loading...</p>;

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Password Authentication</h3>
        <p className="text-xs text-muted-foreground mb-4">Always enabled as the baseline auth method.</p>
        <SettingsForm
          fields={[
            { key: 'auth.password.min_length', label: 'Minimum password length', type: 'number', placeholder: '12' },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      </div>

      <div className="border-t pt-6">
        <h3 className="text-sm font-semibold text-foreground mb-1">Google OAuth</h3>
        <p className="text-xs text-muted-foreground mb-4">Optional. Let users sign in with their Google account.</p>
        <SettingsForm
          fields={[
            { key: 'auth.google.client_id', label: 'Client ID', type: 'text', placeholder: 'your-client-id.apps.googleusercontent.com' },
            { key: 'auth.google.client_secret', label: 'Client secret', type: 'password', is_secret: true },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      </div>

      <div className="border-t pt-6">
        <h3 className="text-sm font-semibold text-foreground mb-1">Microsoft Entra</h3>
        <p className="text-xs text-muted-foreground mb-4">Optional. Let users sign in with their Microsoft account.</p>
        <SettingsForm
          fields={[
            { key: 'auth.microsoft.tenant', label: 'Tenant', type: 'text', placeholder: 'common' },
            { key: 'auth.microsoft.client_id', label: 'Client ID', type: 'text' },
            { key: 'auth.microsoft.client_secret', label: 'Client secret', type: 'password', is_secret: true },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      </div>

      <div className="border-t pt-6">
        <h3 className="text-sm font-semibold text-foreground mb-1">Access Control</h3>
        <SettingsForm
          fields={[
            { key: 'auth.allowed_domains', label: 'Allowed email domains', type: 'text', placeholder: 'yourdomain.com, partner.com', help: 'Comma-separated. Leave empty to allow all domains.' },
            { key: 'auth.allowed_emails', label: 'Allowed emails', type: 'text', placeholder: 'specific@email.com', help: 'Comma-separated. Leave empty to allow all emails.' },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
//  Tab: Email
// ---------------------------------------------------------------------------

function EmailTab({ values, onChange, loaded }: SettingsTabProps) {
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const settings = Object.entries(values)
        .filter(([k]) => k.startsWith('email.'))
        .map(([key, value]) => ({
          key, value,
          is_secret: key.includes('password') || key.includes('secret') || key.includes('api_key'),
        }));
      const result = await updatePlatformSettings(settings);
      toast.success(`${result.updated} settings saved`);
    } catch { toast.error('Failed to save settings'); }
    finally { setSaving(false); }
  };

  if (!loaded) return <p className="text-sm text-muted-foreground p-4">Loading...</p>;

  const provider = values['email.provider'] || '';

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Email Provider</h3>
        <p className="text-xs text-muted-foreground mb-4">Enables login codes (OTP), password reset, and invitations.</p>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {['smtp', 'ses', 'sendgrid', 'resend'].map((p) => (
            <button
              key={p}
              onClick={() => onChange('email.provider', p)}
              className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                provider === p ? 'border-indigo-400 bg-indigo-50 font-medium' : 'border-input hover:border-gray-400'
              }`}
            >
              {p === 'smtp' ? 'SMTP' : p === 'ses' ? 'AWS SES' : p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {provider === 'smtp' && (
        <SettingsForm
          fields={[
            { key: 'email.smtp.host', label: 'Host', type: 'text', placeholder: 'smtp.gmail.com' },
            { key: 'email.smtp.port', label: 'Port', type: 'text', placeholder: '587' },
            { key: 'email.smtp.username', label: 'Username', type: 'text' },
            { key: 'email.smtp.password', label: 'Password', type: 'password', is_secret: true },
            { key: 'email.from_address', label: 'From address', type: 'email', placeholder: 'noreply@yourdomain.com' },
            { key: 'email.from_name', label: 'From name', type: 'text', placeholder: 'Agience' },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      )}

      {(provider === 'sendgrid' || provider === 'resend') && (
        <SettingsForm
          fields={[
            { key: `email.${provider}.api_key`, label: 'API key', type: 'password', is_secret: true },
            { key: 'email.from_address', label: 'From address', type: 'email', placeholder: 'noreply@yourdomain.com' },
            { key: 'email.from_name', label: 'From name', type: 'text', placeholder: 'Agience' },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      )}

      {provider === 'ses' && (
        <SettingsForm
          fields={[
            { key: 'email.ses.region', label: 'Region', type: 'text', placeholder: 'us-east-1' },
            { key: 'email.ses.access_key_id', label: 'Access key ID', type: 'text' },
            { key: 'email.ses.secret_access_key', label: 'Secret access key', type: 'password', is_secret: true },
            { key: 'email.from_address', label: 'From address', type: 'email', placeholder: 'noreply@yourdomain.com' },
            { key: 'email.from_name', label: 'From name', type: 'text', placeholder: 'Agience' },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      )}

      {!provider && (
        <p className="text-sm text-muted-foreground">
          No email provider configured. Users can only sign in with passwords — no OTP, no password reset.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
//  Tab: AI & Search
// ---------------------------------------------------------------------------

function AISearchTab({ values, onChange, loaded }: SettingsTabProps) {
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const settings = Object.entries(values)
        .filter(([k]) => k.startsWith('ai.') || k.startsWith('search.'))
        .map(([key, value]) => ({
          key, value,
          is_secret: key.includes('api_key'),
        }));
      const result = await updatePlatformSettings(settings);
      toast.success(`${result.updated} settings saved`);
    } catch { toast.error('Failed to save settings'); }
    finally { setSaving(false); }
  };

  if (!loaded) return <p className="text-sm text-muted-foreground p-4">Loading...</p>;

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">OpenAI</h3>
        <p className="text-xs text-muted-foreground mb-4">Required for embeddings and AI features.</p>
        <SettingsForm
          fields={[
            { key: 'ai.openai_api_key', label: 'API key', type: 'password', placeholder: 'sk-...', is_secret: true },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      </div>

      <div className="border-t pt-6">
        <h3 className="text-sm font-semibold text-foreground mb-1">Search Tuning</h3>
        <p className="text-xs text-muted-foreground mb-4">Advanced. Defaults work well for most use cases.</p>
        <SettingsForm
          fields={[
            { key: 'search.chunk_size', label: 'Chunk size (tokens)', type: 'number', placeholder: '1000' },
            { key: 'search.chunk_overlap', label: 'Chunk overlap (tokens)', type: 'number', placeholder: '200' },
            { key: 'search.field_weights_preset', label: 'Field weights preset', type: 'text', placeholder: 'description-first', help: 'Options: description-first, balanced, content-heavy' },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
//  Tab: Storage
// ---------------------------------------------------------------------------

function StorageTab({ values, onChange, loaded }: SettingsTabProps) {
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const settings = Object.entries(values)
        .filter(([k]) => k.startsWith('storage.'))
        .map(([key, value]) => ({
          key, value,
          is_secret: key.includes('secret') || key.includes('key_id'),
        }));
      const result = await updatePlatformSettings(settings);
      toast.success(`${result.updated} settings saved`);
      if (result.restart_required) toast('Some changes require a restart to take effect.', { duration: 5000 });
    } catch { toast.error('Failed to save settings'); }
    finally { setSaving(false); }
  };

  if (!loaded) return <p className="text-sm text-muted-foreground p-4">Loading...</p>;

  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground mb-1">Content Storage (S3/MinIO)</h3>
      <p className="text-xs text-muted-foreground mb-4">Where uploaded files are stored. Docker defaults work for local development.</p>
      <SettingsForm
        fields={[
          { key: 'storage.content_uri', label: 'Endpoint URL', type: 'text', placeholder: 'http://localhost:9000' },
          { key: 'storage.content_bucket', label: 'Bucket name', type: 'text', placeholder: 'agience-content' },
          { key: 'storage.aws_access_key_id', label: 'Access key ID', type: 'text', is_secret: true },
          { key: 'storage.aws_secret_access_key', label: 'Secret access key', type: 'password', is_secret: true },
        ]}
        values={values} onChange={onChange} onSave={handleSave} saving={saving}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
//  Tab: Infrastructure
// ---------------------------------------------------------------------------

function InfrastructureTab({ values, onChange, loaded }: SettingsTabProps) {
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const settings = Object.entries(values)
        .filter(([k]) => k.startsWith('db.') || k.startsWith('search.opensearch'))
        .map(([key, value]) => ({
          key, value,
          is_secret: key.includes('password'),
        }));
      const result = await updatePlatformSettings(settings);
      toast.success(`${result.updated} settings saved`);
      if (result.restart_required) {
        toast('These changes require a restart to take effect.', { duration: 8000 });
      }
    } catch { toast.error('Failed to save settings'); }
    finally { setSaving(false); }
  };

  if (!loaded) return <p className="text-sm text-muted-foreground p-4">Loading...</p>;

  return (
    <div className="space-y-8">
      <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
        Changes to database connections require a restart to take effect.
      </div>

      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">ArangoDB</h3>
        <SettingsForm
          fields={[
            { key: 'db.arango.host', label: 'Host', type: 'text', placeholder: 'arangodb' },
            { key: 'db.arango.port', label: 'Port', type: 'text', placeholder: '8529' },
            { key: 'db.arango.password', label: 'Root password', type: 'password', is_secret: true },
            { key: 'db.arango.database', label: 'Database', type: 'text', placeholder: 'agience' },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      </div>

      <div className="border-t pt-6">
        <h3 className="text-sm font-semibold text-foreground mb-1">OpenSearch</h3>
        <SettingsForm
          fields={[
            { key: 'search.opensearch.host', label: 'Host', type: 'text', placeholder: 'search' },
            { key: 'search.opensearch.port', label: 'Port', type: 'text', placeholder: '9200' },
            { key: 'search.opensearch.username', label: 'Username', type: 'text' },
            { key: 'search.opensearch.password', label: 'Password', type: 'password', is_secret: true },
          ]}
          values={values} onChange={onChange} onSave={handleSave} saving={saving}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
//  Tab: Branding
// ---------------------------------------------------------------------------

function BrandingTab({ values, onChange, loaded }: SettingsTabProps) {
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const settings = Object.entries(values)
        .filter(([k]) => k.startsWith('branding.'))
        .map(([key, value]) => ({ key, value }));
      const result = await updatePlatformSettings(settings);
      toast.success(`${result.updated} settings saved`);
    } catch { toast.error('Failed to save settings'); }
    finally { setSaving(false); }
  };

  if (!loaded) return <p className="text-sm text-muted-foreground p-4">Loading...</p>;

  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground mb-1">Platform Branding</h3>
      <p className="text-xs text-muted-foreground mb-4">Customize the look and feel of your platform.</p>
      <SettingsForm
        fields={[
          { key: 'branding.title', label: 'Platform name', type: 'text', placeholder: 'Agience' },
          { key: 'branding.frontend_uri', label: 'Frontend URL', type: 'text', placeholder: 'http://localhost:5173' },
          { key: 'branding.backend_uri', label: 'Backend URL', type: 'text', placeholder: 'http://localhost:8081' },
        ]}
        values={values} onChange={onChange} onSave={handleSave} saving={saving}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
//  Main Page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const isAdmin = useAdmin();
  const { loading: authLoading } = useAuth();
  const navigate = useNavigate();

  // Shared settings state — loaded once, passed to all settings tabs
  const [values, setValues] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  // Guard: redirect non-admin users.
  // Wait for auth to resolve (authLoading=false) before redirecting — the hook
  // defaults to false before the token is parsed, so acting on it before auth
  // resolves would incorrectly bounce authenticated users away.
  useEffect(() => {
    if (!authLoading && !isAdmin) {
      navigate('/', { replace: true });
    }
  }, [authLoading, isAdmin, navigate]);

  // Load all settings once at page mount
  useEffect(() => {
    (async () => {
      try {
        const data = await getPlatformSettings();
        const flat: Record<string, string> = {};
        for (const items of Object.values(data.categories)) {
          for (const item of items) {
            if (item.value !== null) flat[item.key] = item.value;
          }
        }
        setValues(flat);
      } catch { /* settings may not exist yet */ }
      setLoaded(true);
    })();
  }, []);

  const handleChange = useCallback((key: string, value: string) => {
    setValues(v => ({ ...v, [key]: value }));
  }, []);

  // Render nothing while auth is still resolving or after redirect fires
  if (authLoading || !isAdmin) return null;

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl p-6">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Platform Settings</h1>
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            Back to workspace
          </Button>
        </div>
        <Tabs defaultValue="users">
          <TabsList className="flex-wrap">
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="authentication">Authentication</TabsTrigger>
            <TabsTrigger value="email">Email</TabsTrigger>
            <TabsTrigger value="ai-search">AI & Search</TabsTrigger>
            <TabsTrigger value="storage">Storage</TabsTrigger>
            <TabsTrigger value="infrastructure">Infrastructure</TabsTrigger>
            <TabsTrigger value="branding">Branding</TabsTrigger>
            <TabsTrigger value="seed-content">Seed Content</TabsTrigger>
            <TabsTrigger value="integrations">Integrations</TabsTrigger>
          </TabsList>
          <TabsContent value="users" className="mt-4"><UsersTab /></TabsContent>
          <TabsContent value="authentication" className="mt-4">
            <AuthenticationTab values={values} onChange={handleChange} loaded={loaded} />
          </TabsContent>
          <TabsContent value="email" className="mt-4">
            <EmailTab values={values} onChange={handleChange} loaded={loaded} />
          </TabsContent>
          <TabsContent value="ai-search" className="mt-4">
            <AISearchTab values={values} onChange={handleChange} loaded={loaded} />
          </TabsContent>
          <TabsContent value="storage" className="mt-4">
            <StorageTab values={values} onChange={handleChange} loaded={loaded} />
          </TabsContent>
          <TabsContent value="infrastructure" className="mt-4">
            <InfrastructureTab values={values} onChange={handleChange} loaded={loaded} />
          </TabsContent>
          <TabsContent value="branding" className="mt-4">
            <BrandingTab values={values} onChange={handleChange} loaded={loaded} />
          </TabsContent>
          <TabsContent value="seed-content" className="mt-4"><SeedContentTab /></TabsContent>
          <TabsContent value="integrations" className="mt-4">
            <p className="text-sm text-muted-foreground">Manage platform MCP servers and authorizers. Coming soon.</p>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
