export const VIEWER_KEY = 'text-plain' as const;

export const factory = () =>
  import('./viewer').then((m) => ({ default: m.default }));