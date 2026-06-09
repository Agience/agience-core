// AgienceIcons.tsx
// Custom Agience-branded icons for native resources

import React from 'react';

interface IconProps {
  size?: number;
  className?: string;
}

/**
 * Agience Resources icon - Folder with Agience branding
 * Used for collections and resources from Agience
 */
export const AgienceResourcesIcon: React.FC<IconProps> = ({ size = 16, className = '' }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Folder base */}
    <path
      d="M3 6C3 4.89543 3.89543 4 5 4H9L11 6H19C20.1046 6 21 6.89543 21 8V18C21 19.1046 20.1046 20 19 20H5C3.89543 20 3 19.1046 3 18V6Z"
      fill="currentColor"
      opacity="0.2"
    />
    <path
      d="M3 6C3 4.89543 3.89543 4 5 4H9L11 6H19C20.1046 6 21 6.89543 21 8V18C21 19.1046 20.1046 20 19 20H5C3.89543 20 3 19.1046 3 18V6Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    {/* Agience "A" badge */}
    <circle cx="16" cy="14" r="4.5" fill="#9B7EBD" />
    <text
      x="16"
      y="14"
      textAnchor="middle"
      dominantBaseline="central"
      fill="white"
      fontSize="6"
      fontWeight="bold"
      fontFamily="DM Sans, sans-serif"
    >
      A
    </text>
  </svg>
);

/**
 * Agience Tools icon - Wrench with Agience branding
 * Used for tools and workflows from Agience
 */
export const AgienceToolsIcon: React.FC<IconProps> = ({ size = 16, className = '' }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Wrench tool */}
    <path
      d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"
      fill="currentColor"
      opacity="0.2"
    />
    <path
      d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    {/* Agience "A" badge */}
    <circle cx="18" cy="6" r="3.5" fill="#9B7EBD" />
    <text
      x="18"
      y="6"
      textAnchor="middle"
      dominantBaseline="central"
      fill="white"
      fontSize="5"
      fontWeight="bold"
      fontFamily="DM Sans, sans-serif"
    >
      A
    </text>
  </svg>
);

/**
 * Agience Prompts icon - Document with Agience branding
 * Used for prompts from Agience
 */
export const AgiencePromptsIcon: React.FC<IconProps> = ({ size = 16, className = '' }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Document/notebook */}
    <path
      d="M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"
      fill="currentColor"
      opacity="0.2"
    />
    <path
      d="M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    {/* Prompt lines */}
    <line x1="9" y1="9" x2="15" y2="9" stroke="currentColor" strokeWidth="1" opacity="0.4" />
    <line x1="9" y1="12" x2="15" y2="12" stroke="currentColor" strokeWidth="1" opacity="0.4" />
    <line x1="9" y1="15" x2="13" y2="15" stroke="currentColor" strokeWidth="1" opacity="0.4" />
    {/* Agience "A" badge */}
    <circle cx="17" cy="6" r="3.5" fill="#9B7EBD" />
    <text
      x="17"
      y="6"
      textAnchor="middle"
      dominantBaseline="central"
      fill="white"
      fontSize="5"
      fontWeight="bold"
      fontFamily="DM Sans, sans-serif"
    >
      A
    </text>
  </svg>
);
