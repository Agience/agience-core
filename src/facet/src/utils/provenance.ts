export function formatProvenanceLabel(value?: string | null): string {
  if (!value) return 'Unknown';
  return value
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
