/**
 * Unified Icon Button Component
 * 
 * Square buttons with thin grey border, filled or clear states.
 * Icons centered, white on dark background or black on clear.
 */

import { ButtonHTMLAttributes, forwardRef, ReactNode } from 'react';
import { clsx } from 'clsx';

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Size variant - controls both container and icon size */
  size?: 'xs' | 'sm' | 'md' | 'lg';
  /** Visual variant - filled (dark background) or ghost (clear) */
  variant?: 'filled' | 'ghost';
  /** Icon element (should be a Lucide or react-icons icon component) */
  children: ReactNode;
  /** Whether the button is active/selected */
  active?: boolean;
}

const sizeClasses = {
  xs: {
    container: 'h-5 w-5',
    icon: 'h-3 w-3',
  },
  sm: {
    container: 'h-6 w-6',
    icon: 'h-4 w-4',
  },
  md: {
    container: 'h-8 w-8',
    icon: 'h-5 w-5',
  },
  lg: {
    container: 'h-10 w-10',
    icon: 'h-6 w-6',
  },
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ size = 'md', variant = 'ghost', active = false, className, children, disabled, ...props }, ref) => {
    const sizeConfig = sizeClasses[size];

    return (
      <button
        ref={ref}
        className={clsx(
          // Base styles
          'inline-flex items-center justify-center flex-shrink-0',
          'border border-gray-300',
          'transition-all duration-150',
          'focus:outline-none focus:ring-1 focus:ring-gray-400',
          
          // Square shape
          'rounded-sm',
          
          // Size
          sizeConfig.container,
          
          // Variant styles
          variant === 'filled' || active
            ? 'bg-gray-800 text-white hover:bg-gray-700'
            : 'bg-transparent text-gray-700 hover:bg-gray-100',
          
          // Disabled state
          disabled && 'opacity-40 cursor-not-allowed pointer-events-none',
          
          // Custom classes
          className
        )}
        disabled={disabled}
        {...props}
      >
        <span className={clsx('inline-flex items-center justify-center', sizeConfig.icon)}>
          {children}
        </span>
      </button>
    );
  }
);

IconButton.displayName = 'IconButton';

/**
 * IconBadge - For status indicators and non-interactive icon displays
 * Simple rounded badges with solid colors
 */
export interface IconBadgeProps {
  /** Size variant */
  size?: 'xs' | 'sm' | 'md' | 'lg';
  /** Color variant */
  variant?: 'default' | 'info' | 'success' | 'warning' | 'danger';
  /** Icon element */
  children: ReactNode;
  /** Additional CSS classes */
  className?: string;
}

const badgeVariants = {
  default: 'bg-purple-100 border border-purple-300 text-purple-700',
  info: 'bg-blue-100 border border-blue-300 text-blue-700',
  success: 'bg-green-100 border border-green-300 text-green-700',
  warning: 'bg-amber-100 border border-amber-300 text-amber-700',
  danger: 'bg-rose-100 border border-rose-300 text-rose-700',
};

export const IconBadge = ({ size = 'sm', variant = 'default', className, children }: IconBadgeProps) => {
  const sizeConfig = sizeClasses[size];

  return (
    <div
      className={clsx(
        'inline-flex items-center justify-center flex-shrink-0 rounded-full',
        sizeConfig.container,
        badgeVariants[variant],
        className
      )}
    >
      <span className={clsx('inline-flex items-center justify-center', sizeConfig.icon)}>
        {children}
      </span>
    </div>
  );
};

IconBadge.displayName = 'IconBadge';
