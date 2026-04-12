import { useState, useEffect } from 'react';
import { FiX, FiDatabase, FiLoader, FiUser, FiSettings as FiSettingsIcon, FiKey, FiCreditCard, FiLink, FiMinusCircle } from 'react-icons/fi';
import { FcGoogle } from 'react-icons/fc';
import { toast } from 'sonner';
import { loadDemoData } from '../../api/agent';
import { LLMKeysTab } from '../settings/LLMKeysTab';
import McpSettingsFrame from '../settings/McpSettingsFrame';
import { get } from '../../api/api';
import { useAuth } from '../../hooks/useAuth';
import type { Artifact } from '@/context/workspace/workspace.types';

type ArtifactOpenOptions = {
  startInEditMode?: boolean;
};

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialSection?: SettingsSection;
  scopedToCollectionId?: string;
  onArtifactCreated?: (artifact: Artifact, options?: ArtifactOpenOptions) => void;
}

type SettingsSection = 'profile' | 'general' | 'llm-keys' | 'billing' | 'demo-data';

interface SettingsSectionConfig {
  id: SettingsSection;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const SETTINGS_SECTIONS: SettingsSectionConfig[] = [
  { id: 'profile', label: 'Profile', icon: FiUser },
  { id: 'general', label: 'General', icon: FiSettingsIcon },
  { id: 'llm-keys', label: 'LLM Keys', icon: FiKey },
  { id: 'billing', label: 'Billing', icon: FiCreditCard },
  { id: 'demo-data', label: 'Demo Data', icon: FiDatabase },
];

export default function SettingsModal({ isOpen, onClose, initialSection }: SettingsModalProps) {
  const [activeSection, setActiveSection] = useState<SettingsSection>(initialSection || 'profile');
  const [isGenerating, setIsGenerating] = useState(false);

  // Update active section when initialSection changes
  useEffect(() => {
    if (initialSection) {
      setActiveSection(initialSection);
    }
  }, [initialSection]);
  const [numWorkspaces, setNumWorkspaces] = useState(3);
  const [artifactsPerWorkspace, setArtifactsPerWorkspace] = useState(5);
  const [includeAgienceGuide, setIncludeAgienceGuide] = useState(true);
  const [customTopics, setCustomTopics] = useState('');

  if (!isOpen) return null;

  const handleGenerateDemoData = async () => {
    setIsGenerating(true);
    try {
      const topics = customTopics.trim()
        ? customTopics.split(',').map(t => t.trim()).filter(Boolean)
        : undefined;

      const result = await loadDemoData({
        topics,
        num_workspaces: numWorkspaces,
        artifacts_per_workspace: artifactsPerWorkspace,
        include_agience_guide: includeAgienceGuide,
      });

      toast.success(
        `Created ${result.workspaces_created} workspaces with ${result.workspace_artifacts_created} artifacts!${result.agience_guide_added ? ' Agience Guide added.' : ''}`,
        { duration: 5000 }
      );

      // Reload the page to show new data
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } catch (error: unknown) {
      console.error('Failed to generate demo data:', error);
      const errorMessage = error instanceof Error && 'response' in error && error.response
        ? (error.response as { data?: { detail?: string } }).data?.detail || 'Failed to generate demo data'
        : 'Failed to generate demo data';
      toast.error(errorMessage);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl mx-4 h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-xl font-semibold text-gray-900">Settings</h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            title="Close"
          >
            <FiX className="w-5 h-5" />
          </button>
        </div>

        {/* Content: Sidebar + Panel with fixed sizing */}
        <div className="flex-1 flex overflow-hidden min-h-0">
          {/* Sidebar - Fixed Width */}
          <div className="w-56 border-r border-gray-200 bg-gray-50 overflow-y-auto flex-shrink-0">
            <nav className="p-3 space-y-1">
              {SETTINGS_SECTIONS.map((section) => {
                const Icon = section.icon;
                const isActive = activeSection === section.id;
                return (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-primary-100 text-primary-700'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    <Icon className="w-5 h-5 flex-shrink-0" />
                    {section.label}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Content Panel - Fixed size, scrollable content */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto p-6">
              {activeSection === 'general' && <GeneralSettings />}
              {activeSection === 'demo-data' && (
                <DemoDataSettings
                  isGenerating={isGenerating}
                  numWorkspaces={numWorkspaces}
                  setNumWorkspaces={setNumWorkspaces}
                  artifactsPerWorkspace={artifactsPerWorkspace}
                  setArtifactsPerWorkspace={setArtifactsPerWorkspace}
                  customTopics={customTopics}
                  setCustomTopics={setCustomTopics}
                  includeAgienceGuide={includeAgienceGuide}
                  setIncludeAgienceGuide={setIncludeAgienceGuide}
                  onGenerate={handleGenerateDemoData}
                />
              )}
              {activeSection === 'profile' && <ProfileSettings />}
              {activeSection === 'llm-keys' && <LLMKeysTab />}
              {activeSection === 'billing' && (
                <McpSettingsFrame
                  server="ophan"
                  resourceUri="ui://ophan/billing-settings.html"
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// General Settings Section
function GeneralSettings() {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">General Settings</h3>
        <p className="text-sm text-gray-600">
          General application preferences and configurations.
        </p>
      </div>
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center text-gray-500">
        Coming soon...
      </div>
    </div>
  );
}

// Profile Settings Section
function ProfileSettings() {
  const { user, startLinkProvider, unlinkProvider } = useAuth();
  const [googleAvailable, setGoogleAvailable] = useState(false);
  const [unlinkPending, setUnlinkPending] = useState(false);

  useEffect(() => {
    // Check which providers the platform has configured
    get<string[]>('/auth/providers')
      .then((providers) => setGoogleAvailable(providers.includes('google')))
      .catch(() => {/* silent — providers endpoint may not be mounted in all setups */});
  }, []);

  const linkedToGoogle =
    user?.oidc_provider === 'google' && Boolean(user?.oidc_provider);
  const canUnlink = linkedToGoogle && user?.has_password;
  const canLink = googleAvailable && !linkedToGoogle;

  const handleUnlink = async () => {
    setUnlinkPending(true);
    try {
      await unlinkProvider('google');
      toast.success('Google account unlinked.');
    } catch {
      toast.error('Failed to unlink Google account.');
    } finally {
      setUnlinkPending(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Profile</h3>
        <p className="text-sm text-gray-600">
          Manage your account identity and linked sign-in methods.
        </p>
      </div>

      {/* User info card */}
      <div className="flex items-center gap-4 p-4 bg-gray-50 border border-gray-200 rounded-lg">
        {user?.picture ? (
          <img
            src={user.picture}
            alt={user.name}
            className="w-12 h-12 rounded-full object-cover"
          />
        ) : (
          <div className="w-12 h-12 rounded-full bg-primary-100 flex items-center justify-center">
            <FiUser className="w-6 h-6 text-primary-600" />
          </div>
        )}
        <div>
          <p className="font-medium text-gray-900">{user?.name}</p>
          <p className="text-sm text-gray-500">{user?.email}</p>
        </div>
      </div>

      {/* Linked sign-in methods */}
      <div>
        <h4 className="text-sm font-semibold text-gray-700 mb-3">Sign-in methods</h4>
        <div className="space-y-2">
          {/* Password (if set) */}
          {user?.has_password && (
            <div className="flex items-center justify-between p-3 bg-gray-50 border border-gray-200 rounded-lg">
              <div className="flex items-center gap-3">
                <FiKey className="w-5 h-5 text-gray-500" />
                <span className="text-sm text-gray-800">Email &amp; Password</span>
              </div>
              <span className="text-xs text-green-600 font-medium px-2 py-0.5 bg-green-50 rounded-full">Active</span>
            </div>
          )}

          {/* Google */}
          {linkedToGoogle ? (
            <div className="flex items-center justify-between p-3 bg-gray-50 border border-gray-200 rounded-lg">
              <div className="flex items-center gap-3">
                <FcGoogle className="w-5 h-5" />
                <span className="text-sm text-gray-800">Google</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-green-600 font-medium px-2 py-0.5 bg-green-50 rounded-full">Linked</span>
                {canUnlink && (
                  <button
                    onClick={handleUnlink}
                    disabled={unlinkPending}
                    className="flex items-center gap-1.5 text-xs text-red-600 hover:text-red-700 border border-red-200 hover:bg-red-50 rounded px-2 py-1 transition-colors disabled:opacity-50"
                  >
                    {unlinkPending ? <FiLoader className="w-3 h-3 animate-spin" /> : <FiMinusCircle className="w-3 h-3" />}
                    Unlink
                  </button>
                )}
              </div>
            </div>
          ) : googleAvailable ? (
            <div className="flex items-center justify-between p-3 bg-gray-50 border border-gray-200 rounded-lg">
              <div className="flex items-center gap-3">
                <FcGoogle className="w-5 h-5" />
                <span className="text-sm text-gray-800">Google</span>
              </div>
              {canLink && (
                <button
                  onClick={() => startLinkProvider('google')}
                  className="flex items-center gap-1.5 text-xs text-primary-600 hover:text-primary-700 border border-primary-200 hover:bg-primary-50 rounded px-2 py-1 transition-colors"
                >
                  <FiLink className="w-3 h-3" />
                  Link account
                </button>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// Demo Data Settings Section
interface DemoDataSettingsProps {
  isGenerating: boolean;
  numWorkspaces: number;
  setNumWorkspaces: (value: number) => void;
  artifactsPerWorkspace: number;
  setArtifactsPerWorkspace: (value: number) => void;
  customTopics: string;
  setCustomTopics: (value: string) => void;
  includeAgienceGuide: boolean;
  setIncludeAgienceGuide: (value: boolean) => void;
  onGenerate: () => void;
}

function DemoDataSettings({
  isGenerating,
  numWorkspaces,
  setNumWorkspaces,
  artifactsPerWorkspace,
  setArtifactsPerWorkspace,
  customTopics,
  setCustomTopics,
  includeAgienceGuide,
  setIncludeAgienceGuide,
  onGenerate,
}: DemoDataSettingsProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Generate Demo Data</h3>
        <p className="text-sm text-gray-600">
          Create AI-generated workspace artifacts for testing and experimentation
        </p>
      </div>

      {/* Topics Input */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Topics (Optional)
        </label>
        <input
          type="text"
          value={customTopics}
          onChange={(e) => setCustomTopics(e.target.value)}
          placeholder="AI, Marketing, Product Strategy (comma-separated)"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
        />
        <p className="mt-1 text-xs text-gray-500">
          Leave blank for diverse default topics
        </p>
      </div>

      {/* Workspace generation */}
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Number of Workspaces: {numWorkspaces}
          </label>
          <input
            type="range"
            min="1"
            max="5"
            value={numWorkspaces}
            onChange={(e) => setNumWorkspaces(parseInt(e.target.value))}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>1</span>
            <span>5</span>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Artifacts per Workspace: {artifactsPerWorkspace}
          </label>
          <input
            type="range"
            min="1"
            max="10"
            value={artifactsPerWorkspace}
            onChange={(e) => setArtifactsPerWorkspace(parseInt(e.target.value))}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>1</span>
            <span>10</span>
          </div>
        </div>
      </div>

      {/* Include Agience Guide */}
      <div className="flex items-center gap-3">
        <input
          id="include-guide"
          type="checkbox"
          checked={includeAgienceGuide}
          onChange={(e) => setIncludeAgienceGuide(e.target.checked)}
        />
        <label htmlFor="include-guide" className="text-sm text-gray-700">Include Agience Guide Collection</label>
      </div>

      {/* Warning */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <p className="text-sm text-yellow-800">
          <strong>Note:</strong> This will create new workspaces and artifacts. The page will reload after generation.
        </p>
      </div>

      {/* Generate Button */}
      <div className="flex justify-end">
        <button
          onClick={onGenerate}
          disabled={isGenerating}
          className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {isGenerating ? (
            <>
              <FiLoader className="w-4 h-4 animate-spin" />
              Generating...
            </>
          ) : (
            <>
              <FiDatabase className="w-4 h-4" />
              Generate Demo Data
            </>
          )}
        </button>
      </div>
    </div>
  );
}

