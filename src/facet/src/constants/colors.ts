/**
 * Standardized color constants for the application.
 * Use these instead of arbitrary Tailwind classes to ensure consistency.
 * 
 * Based on standard CSS colors (purple, blue, etc.) with Tailwind shades.
 */

export const Colors = {
  // Primary action color (Purple)
  primary: {
    50: 'bg-purple-50',
    100: 'bg-purple-100',
    200: 'bg-purple-200',
    300: 'bg-purple-300',
    400: 'bg-purple-400',
    500: 'bg-purple-500',
    600: 'bg-purple-600',
    700: 'bg-purple-700',
    800: 'bg-purple-800',
    900: 'bg-purple-900',
  },

  // Secondary action color (Blue)
  secondary: {
    50: 'bg-blue-50',
    100: 'bg-blue-100',
    200: 'bg-blue-200',
    300: 'bg-blue-300',
    400: 'bg-blue-400',
    500: 'bg-blue-500',
    600: 'bg-blue-600',
    700: 'bg-blue-700',
    800: 'bg-blue-800',
    900: 'bg-blue-900',
  },

  // Success/New state (Green)
  success: {
    50: 'bg-green-50',
    100: 'bg-green-100',
    200: 'bg-green-200',
    300: 'bg-green-300',
    400: 'bg-green-400',
    500: 'bg-green-500',
    600: 'bg-green-600',
    700: 'bg-green-700',
    800: 'bg-green-800',
    900: 'bg-green-900',
  },

  // Warning/Modified state (Amber)
  warning: {
    50: 'bg-amber-50',
    100: 'bg-amber-100',
    200: 'bg-amber-200',
    300: 'bg-amber-300',
    400: 'bg-amber-400',
    500: 'bg-amber-500',
    600: 'bg-amber-600',
    700: 'bg-amber-700',
    800: 'bg-amber-800',
    900: 'bg-amber-900',
  },

  // Danger/Archived state (Red)
  danger: {
    50: 'bg-red-50',
    100: 'bg-red-100',
    200: 'bg-red-200',
    300: 'bg-red-300',
    400: 'bg-red-400',
    500: 'bg-red-500',
    600: 'bg-red-600',
    700: 'bg-red-700',
    800: 'bg-red-800',
    900: 'bg-red-900',
  },

  // Neutral/Gray scale
  neutral: {
    50: 'bg-gray-50',
    100: 'bg-gray-100',
    200: 'bg-gray-200',
    300: 'bg-gray-300',
    400: 'bg-gray-400',
    500: 'bg-gray-500',
    600: 'bg-gray-600',
    700: 'bg-gray-700',
    800: 'bg-gray-800',
    900: 'bg-gray-900',
  },
} as const;

/**
 * Text color variants
 */
export const TextColors = {
  primary: {
    50: 'text-purple-50',
    100: 'text-purple-100',
    200: 'text-purple-200',
    300: 'text-purple-300',
    400: 'text-purple-400',
    500: 'text-purple-500',
    600: 'text-purple-600',
    700: 'text-purple-700',
    800: 'text-purple-800',
    900: 'text-purple-900',
  },
  secondary: {
    50: 'text-blue-50',
    100: 'text-blue-100',
    200: 'text-blue-200',
    300: 'text-blue-300',
    400: 'text-blue-400',
    500: 'text-blue-500',
    600: 'text-blue-600',
    700: 'text-blue-700',
    800: 'text-blue-800',
    900: 'text-blue-900',
  },
  success: {
    50: 'text-green-50',
    100: 'text-green-100',
    200: 'text-green-200',
    300: 'text-green-300',
    400: 'text-green-400',
    500: 'text-green-500',
    600: 'text-green-600',
    700: 'text-green-700',
    800: 'text-green-800',
    900: 'text-green-900',
  },
  warning: {
    50: 'text-amber-50',
    100: 'text-amber-100',
    200: 'text-amber-200',
    300: 'text-amber-300',
    400: 'text-amber-400',
    500: 'text-amber-500',
    600: 'text-amber-600',
    700: 'text-amber-700',
    800: 'text-amber-800',
    900: 'text-amber-900',
  },
  danger: {
    50: 'text-red-50',
    100: 'text-red-100',
    200: 'text-red-200',
    300: 'text-red-300',
    400: 'text-red-400',
    500: 'text-red-500',
    600: 'text-red-600',
    700: 'text-red-700',
    800: 'text-red-800',
    900: 'text-red-900',
  },
  neutral: {
    50: 'text-gray-50',
    100: 'text-gray-100',
    200: 'text-gray-200',
    300: 'text-gray-300',
    400: 'text-gray-400',
    500: 'text-gray-500',
    600: 'text-gray-600',
    700: 'text-gray-700',
    800: 'text-gray-800',
    900: 'text-gray-900',
  },
} as const;

/**
 * Border color variants
 */
export const BorderColors = {
  primary: {
    200: 'border-purple-200',
    300: 'border-purple-300',
    400: 'border-purple-400',
    500: 'border-purple-500',
    600: 'border-purple-600',
  },
  secondary: {
    200: 'border-blue-200',
    300: 'border-blue-300',
    400: 'border-blue-400',
    500: 'border-blue-500',
    600: 'border-blue-600',
  },
  neutral: {
    200: 'border-gray-200',
    300: 'border-gray-300',
    400: 'border-gray-400',
    500: 'border-gray-500',
    600: 'border-gray-600',
  },
} as const;

/**
 * Common color combinations for buttons
 */
export const ButtonStyles = {
  // Primary action button (purple)
  primary: 'bg-purple-600 hover:bg-purple-700 text-white',
  primaryDisabled: 'bg-purple-400 text-white cursor-not-allowed',
  
  // Secondary action button (blue)
  secondary: 'bg-blue-600 hover:bg-blue-700 text-white',
  secondaryDisabled: 'bg-blue-400 text-white cursor-not-allowed',
  
  // Success button (green)
  success: 'bg-green-600 hover:bg-green-700 text-white',
  
  // Danger button (red)
  danger: 'bg-red-600 hover:bg-red-700 text-white',
  
  // Neutral/Ghost button
  ghost: 'bg-transparent hover:bg-gray-100 text-gray-700 border border-gray-300',
  
  // Icon-only button
  icon: 'p-2 text-gray-600 hover:bg-gray-100 rounded transition-colors',
} as const;

/**
 * Artifact state colors
 */
export const ArtifactStateColors = {
  draft: {
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-green-300',
  },
  committed: {
    bg: 'bg-gray-50',
    text: 'text-gray-700',
    border: 'border-gray-300',
  },
  archived: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-300',
  },
} as const;
