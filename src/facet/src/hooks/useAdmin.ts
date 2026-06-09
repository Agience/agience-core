import { useAuth } from './useAuth';

export function useAdmin(): boolean {
  const { user } = useAuth();
  return user?.roles?.includes('platform:admin') ?? false;
}
