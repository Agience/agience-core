export const VIEWER_KEY = 'text-markdown' as const;

export const factory = () =>
  import('./viewer').then((m) => ({ default: m.default }));