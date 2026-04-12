// frontend/src/components/settings/LLMKeysTab.tsx
import React, { useState, useEffect } from 'react';
import { Trash2, Plus, Star, CheckCircle2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { IconButton } from '../ui/icon-button';
import {
  listSecrets,
  addSecret,
  deleteSecret,
  setDefaultSecret,
  SecretResponse,
} from '../../api/secrets';
import { LLM_PROVIDERS } from '../../constants/llm';

interface AddKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const AddKeyModal: React.FC<AddKeyModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const [provider, setProvider] = useState('openai');
  const [label, setLabel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [isDefault, setIsDefault] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!provider || !label || !apiKey) {
      toast.error('Please fill in all fields');
      return;
    }

    setIsSubmitting(true);
    try {
      await addSecret({
        type: 'llm_key',
        provider,
        label,
        value: apiKey,
        is_default: isDefault,
      });
      toast.success('API key added successfully');
      onSuccess();
      onClose();
      // Reset form
      setProvider('openai');
      setLabel('');
      setApiKey('');
      setIsDefault(false);
    } catch (error) {
      console.error('Failed to add LLM key:', error);
      toast.error('Failed to add API key');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6">
        <h2 className="text-xl font-semibold mb-4 dark:text-white">Add API Key</h2>
        
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            {/* Provider */}
            <div>
              <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                Provider
              </label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              >
                {Object.entries(LLM_PROVIDERS).map(([key, name]) => (
                  <option key={key} value={key}>
                    {name}
                  </option>
                ))}
              </select>
            </div>

            {/* Label */}
            <div>
              <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                Label
              </label>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="My OpenAI Key"
                className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              />
            </div>

            {/* API Key */}
            <div>
              <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                API Key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-proj-..."
                className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white font-mono text-sm"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Your key is encrypted and never exposed
              </p>
            </div>

            {/* Set as Default */}
            <div className="flex items-center">
              <input
                type="checkbox"
                id="isDefault"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="mr-2"
              />
              <label htmlFor="isDefault" className="text-sm dark:text-gray-200">
                Set as default for this provider
              </label>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 mt-6">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {isSubmitting ? 'Adding...' : 'Add Key'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

interface DeleteConfirmModalProps {
  isOpen: boolean;
  keyLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

const DeleteConfirmModal: React.FC<DeleteConfirmModalProps> = ({
  isOpen,
  keyLabel,
  onConfirm,
  onCancel,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6">
        <h2 className="text-xl font-semibold mb-4 dark:text-white">Delete API Key</h2>
        <p className="text-gray-700 dark:text-gray-300 mb-6">
          Are you sure you want to delete <strong>{keyLabel}</strong>? This action cannot be undone.
        </p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
};

export const LLMKeysTab: React.FC = () => {
  const [keys, setKeys] = useState<SecretResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; label: string } | null>(null);

  const loadKeys = async () => {
    try {
      const data = await listSecrets('llm_key');
      setKeys(data);
    } catch (error) {
      console.error('Failed to load LLM keys:', error);
      toast.error('Failed to load API keys');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadKeys();
  }, []);

  const handleSetDefault = async (keyId: string) => {
    try {
      await setDefaultSecret(keyId);
      toast.success('Default key updated');
      loadKeys();
    } catch (error) {
      console.error('Failed to set default key:', error);
      toast.error('Failed to set default key');
    }
  };

  const handleDelete = async (keyId: string) => {
    try {
      await deleteSecret(keyId);
      toast.success('API key deleted');
      setDeleteConfirm(null);
      loadKeys();
    } catch (error) {
      console.error('Failed to delete key:', error);
      toast.error('Failed to delete key');
    }
  };

  const formatDate = (isoDate: string) => {
    return new Date(isoDate).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 dark:text-gray-400">Loading API keys...</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-lg font-semibold dark:text-white">LLM API Keys</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Bring your own OpenAI, Anthropic, or other LLM provider keys
          </p>
        </div>
        <button
          onClick={() => setIsAddModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-md transition-all bg-gradient-to-br from-purple-400/20 via-pink-400/20 to-blue-400/20 hover:from-purple-500/30 hover:via-pink-500/30 hover:to-blue-500/30 border border-purple-200/40 text-purple-700 font-medium"
        >
          <Plus size={16} />
          Add Key
        </button>
      </div>

      {keys.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed rounded-lg dark:border-gray-700">
          <p className="text-gray-500 dark:text-gray-400 mb-4">No API keys added yet</p>
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="text-blue-600 hover:underline"
          >
            Add your first key
          </button>
        </div>
      ) : (
        <div className="border rounded-lg overflow-hidden dark:border-gray-700">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Provider
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Label
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Created
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Default
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-gray-700">
              {keys.map((key) => (
                <tr key={key.id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                      {LLM_PROVIDERS[key.provider as keyof typeof LLM_PROVIDERS] || key.provider}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm dark:text-gray-200">{key.label}</td>
                  <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                    {formatDate(key.created_time)}
                  </td>
                  <td className="px-4 py-3">
                    {key.is_default ? (
                      <CheckCircle2 size={16} className="text-green-600 dark:text-green-400" />
                    ) : (
                      <IconButton
                        size="sm"
                        variant="ghost"
                        onClick={() => handleSetDefault(key.id)}
                        title="Set as default"
                      >
                        <Star size={16} />
                      </IconButton>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <IconButton
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleteConfirm({ id: key.id, label: key.label })}
                      title="Delete key"
                    >
                      <Trash2 size={16} />
                    </IconButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modals */}
      <AddKeyModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSuccess={loadKeys}
      />
      <DeleteConfirmModal
        isOpen={deleteConfirm !== null}
        keyLabel={deleteConfirm?.label || ''}
        onConfirm={() => deleteConfirm && handleDelete(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  );
};
