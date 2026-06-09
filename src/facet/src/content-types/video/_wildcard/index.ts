export const VIEWER_KEY = 'video' as const;

export const factory = () =>
  import('./viewer').then((m) => ({ default: m.default }));