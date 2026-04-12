export const VIEWER_KEY = 'audio' as const;

export const factory = () =>
  import('./viewer').then((m) => ({ default: m.default }));