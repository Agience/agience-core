/**
 * useUpgradePrompt — listens for 402 (payment required) events
 * dispatched by the API interceptor and shows contextual upgrade toasts.
 */

import { useEffect } from 'react';
import { toast } from 'sonner';

interface UpgradePromptDetail {
  reason: string;
  code?: string;
  limit?: number;
  used?: number;
}

const REASON_MESSAGES: Record<string, string> = {
  workspace_limit: 'You\'ve reached your workspace limit.',
  artifact_limit: 'You\'ve reached your artifact limit.',
  vu_limit: 'You\'ve used all your processing units this month.',
};

export function useUpgradePrompt() {
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<UpgradePromptDetail>).detail;
      if (!detail?.reason) return;

      const message = REASON_MESSAGES[detail.reason] || 'You\'ve reached a plan limit.';

      toast.error(message, {
        description: detail.limit
          ? `Current usage: ${detail.used ?? '?'} / ${detail.limit}.`
          : 'Upgrade your plan for higher limits.',
        action: {
          label: 'Upgrade',
          onClick: () => {
            window.dispatchEvent(
              new CustomEvent('agience:open-settings', { detail: { section: 'billing' } }),
            );
          },
        },
        duration: 8000,
      });
    };

    window.addEventListener('agience:upgrade-prompt', handler);
    return () => window.removeEventListener('agience:upgrade-prompt', handler);
  }, []);
}
