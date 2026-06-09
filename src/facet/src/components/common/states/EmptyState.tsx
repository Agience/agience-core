import { StateMessage, type StateMessageProps } from './StateMessage';

type EmptyStateProps = Omit<StateMessageProps, 'variant' | 'icon' | 'title'> & {
  title?: string;
  description?: string;
};

export function EmptyState({
  title = 'Nothing to show yet',
  description = 'Add content or adjust your filters to see results here.',
  ...rest
}: EmptyStateProps) {
  return (
    <StateMessage
      variant="empty"
      title={title}
      description={description}
      {...rest}
    />
  );
}
