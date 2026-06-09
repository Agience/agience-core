import { StateMessage, type StateMessageProps } from './StateMessage';

type BlockedStateProps = Omit<StateMessageProps, 'variant' | 'icon' | 'title'> & {
  title?: string;
  description?: string;
};

export function BlockedState({
  title = 'This action is read-only',
  description = 'You do not have permission to modify these items. Contact an owner or choose a different target.',
  ...rest
}: BlockedStateProps) {
  return (
    <StateMessage
      variant="blocked"
      title={title}
      description={description}
      {...rest}
    />
  );
}
