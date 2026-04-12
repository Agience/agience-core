export const VIEWER_KEY = 'application-pdf' as const;

export const factory = () =>
  import('./viewer').then((m) => ({ default: m.default }));