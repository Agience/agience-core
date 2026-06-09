import { ReactNode } from 'react';
import { AlertTriangle, Inbox, Loader2, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';

type StateVariant = 'loading' | 'empty' | 'error' | 'blocked';

type Alignment = 'center' | 'start';

type StateMessageProps = {
  title: string;
  description?: string;
  icon?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  variant?: StateVariant;
  align?: Alignment;
  density?: 'default' | 'compact';
};

const VARIANT_ICON: Record<StateVariant, ReactNode> = {
  loading: <Loader2 className="h-10 w-10 text-primary-600 animate-spin" aria-hidden="true" />,
  empty: <Inbox className="h-10 w-10 text-gray-400" aria-hidden="true" />,
  error: <AlertTriangle className="h-10 w-10 text-rose-500" aria-hidden="true" />,
  blocked: <ShieldAlert className="h-10 w-10 text-amber-500" aria-hidden="true" />,
};

export function StateMessage({
  title,
  description,
  icon,
  actions,
  children,
  className,
  variant = 'empty',
  align = 'center',
  density = 'default',
}: StateMessageProps) {
  const derivedIcon = icon ?? VARIANT_ICON[variant];
  const alignmentClasses = align === 'center'
    ? 'items-center text-center'
    : 'items-start text-left';
  const spacingClasses = density === 'compact' ? 'py-6 px-4' : 'py-12 px-6';

  return (
    <section
      className={cn(
        'flex flex-col gap-4 justify-center text-sm text-muted-foreground',
        spacingClasses,
        alignmentClasses,
        className,
      )}
      aria-live={variant === 'loading' ? 'polite' : undefined}
    >
      {derivedIcon}
      <div className={cn('flex flex-col gap-1 max-w-lg', align === 'center' ? 'items-center' : 'items-start')}>
        <h3 className="text-lg font-semibold text-foreground">{title}</h3>
        {description ? (
          <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
        ) : null}
        {children}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </section>
  );
}

export type { StateMessageProps, StateVariant };
