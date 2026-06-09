import { StateMessage, type StateMessageProps } from './StateMessage';

type LoadingStateProps = Omit<StateMessageProps, 'variant' | 'icon' | 'title'> & {
  title?: string;
  description?: string;
};

export function LoadingState({
  title = 'Loading...',
  description,
  ...rest
}: LoadingStateProps) {
  return (
    <StateMessage
      variant="loading"
      title={title}
      description={description ?? 'Fetching the latest information. Hang tight.'}
      {...rest}
    />
  );
}
