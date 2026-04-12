export const VIEWER_KEY = 'application-json' as const;

export const factory = () =>
  import('./viewer').then((m) => ({ default: m.default }));