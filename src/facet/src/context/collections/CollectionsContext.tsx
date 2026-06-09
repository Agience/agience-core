import { createStrictContext } from '../../utils/createStrictContext';
import { Collection } from './collection.types';

export interface CollectionsContextType {
  collections: Collection[];
  addSharedCollection: (name: string) => Promise<void>;
  isEditModalOpen: boolean;
  openEditModal: () => void;
  closeEditModal: () => void;
  isLoading: boolean;
}

export const [CollectionsContext, useCollections] = createStrictContext<CollectionsContextType>('CollectionsContext');
