import { createContext, useContext } from 'react';

export function createStrictContext<T>(name: string) {
  const ctx = createContext<T | null>(null);
  const useCtx = () => {
    const value = useContext(ctx);
    if (!value) throw new Error(`${name} must be used within ${name}Provider`);
    return value;
  };
  return [ctx, useCtx] as const;
}
