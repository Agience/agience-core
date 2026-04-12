import { ReactNode, useState, useEffect, useCallback } from 'react';
import { CollectionsContext } from './CollectionsContext';
import { Collection } from './collection.types';
import { useAuth } from '../../hooks/useAuth';
import {
  listCollections,
  createCollection,
} from '../../api/collections';

export const CollectionsProvider = ({ children }: { children: ReactNode }) => {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const hasGrantKeys = (() => {
    // Check grant_keys storage key.
    const raw = sessionStorage.getItem('grant_keys') ?? localStorage.getItem('grant_keys');
    if (!raw) return false;
    try {
      const val = JSON.parse(raw);
      return Array.isArray(val) && val.length > 0;
    } catch {
      return false;
    }
  })();

  useEffect(() => {
    if (authLoading) return;
    if (!isAuthenticated && !hasGrantKeys) return;

    setIsLoading(true);
    listCollections()
      .then(setCollections)
      .catch((err) => {
        console.error('Failed to fetch collections', err);
      })
      .finally(() => setIsLoading(false));
  }, [authLoading, isAuthenticated, hasGrantKeys]);

  const addSharedCollection = useCallback(async (name: string) => {
    try {
      const created = await createCollection({ name });
      setCollections((prev) => [...prev, created]);
    } catch (err) {
      console.error('Failed to create collection', err);
    }
  }, []);

  const value = {
    collections,
    addSharedCollection,
    isEditModalOpen,
    openEditModal: () => setIsEditModalOpen(true),
    closeEditModal: () => setIsEditModalOpen(false),
    isLoading,
  };

  return (
    <CollectionsContext.Provider value={value}>
      {children}
    </CollectionsContext.Provider>
  );
};
