/**
 * LLM display constants — provider labels and model catalogs.
 *
 * These are static UI data used by settings components to render
 * provider/model dropdowns. They are not API calls; they do not belong
 * in `src/api/`. Per-workspace LLM config lives in the workspace
 * artifact's `context.llm` block and is set via the generic
 * `updateArtifact(workspaceId, { context: { llm: {...} } })` call.
 */

export interface WorkspaceLLMConfig {
  provider: string;
  model: string;
  key_id?: string;
}

/**
 * Provider display names.
 */
export const LLM_PROVIDERS = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  azure: 'Azure OpenAI',
  google: 'Google AI',
  cohere: 'Cohere',
  mistral: 'Mistral AI',
  local: 'Local (Ollama)',
} as const;

/**
 * Model options by provider.
 */
export const LLM_MODELS: Record<string, string[]> = {
  openai: [
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4-turbo',
    'gpt-4',
    'gpt-3.5-turbo',
    'o1-preview',
    'o1-mini',
  ],
  anthropic: [
    'claude-3-5-sonnet-20241022',
    'claude-3-5-haiku-20241022',
    'claude-3-opus-20240229',
    'claude-3-sonnet-20240229',
    'claude-3-haiku-20240307',
  ],
  azure: [
    'gpt-4o',
    'gpt-4-turbo',
    'gpt-4',
    'gpt-35-turbo',
  ],
  google: [
    'gemini-2.0-flash',
    'gemini-1.5-pro',
    'gemini-1.5-flash',
  ],
  cohere: [
    'command-r-plus',
    'command-r',
    'command',
  ],
  mistral: [
    'mistral-large-latest',
    'mistral-medium-latest',
    'mistral-small-latest',
  ],
  local: [
    'llama3.3:latest',
    'llama3.2:latest',
    'mistral:latest',
    'qwen2.5:latest',
  ],
};

/**
 * Get default model for a provider.
 */
export function getDefaultModel(provider: string): string {
  const models = LLM_MODELS[provider];
  return models?.[0] || '';
}
