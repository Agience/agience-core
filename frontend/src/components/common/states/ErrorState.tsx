import { ReactNode, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { StateMessage, type StateMessageProps } from './StateMessage';

type ErrorStateProps = Omit<StateMessageProps, 'variant' | 'icon' | 'title'> & {
  title?: string;
  description?: string;
  onRetry?: () => void;
  retryLabel?: string;
  actions?: ReactNode;
};

export function ErrorState({
  title = 'Something went wrong',
  description = 'We hit a snag while processing your request. Please try again.',
  onRetry,
  retryLabel = 'Try again',
  actions,
  ...rest
}: ErrorStateProps) {
  const derivedActions = useMemo(() => {
    if (actions) return actions;
    if (!onRetry) return undefined;

    return (
      <Button onClick={onRetry} variant="outline" size="sm">
        {retryLabel}
      </Button>
    );
  }, [actions, onRetry, retryLabel]);

  return (
    <StateMessage
      variant="error"
      title={title}
      description={description}
      actions={derivedActions}
      {...rest}
    />
  );
}
