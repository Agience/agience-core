export const VIEWER_KEY = 'image' as const;

export const factory = () =>
  import('./viewer').then((m) => ({ default: m.default }));