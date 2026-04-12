// src/components/modal/CardDetailModal.tsx
import { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { useCollections } from '../../hooks/useCollections';
import { Artifact } from '../../context/workspace/workspace.types';
import KeyValueEditor from './KeyValueEditor';
import { useAuth } from '../../hooks/useAuth';
import { ArtifactResponse, ArtifactUpdate } from '../../api/types';
import { addArtifactToCollection, removeArtifactFromCollection } from '../../api/collections';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

type JSONValue = string | number | boolean | null | JSONArray | JSONObject;
type JSONArray = JSONValue[];
type JSONObject = { [key: string]: JSONValue };

const isPlainObject = (v: unknown): v is JSONObject =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

interface ArtifactEditModalProps {
  artifact: Artifact;
  onSave: (updated: ArtifactUpdate) => void;
  onClose: () => void;
}

export default function ArtifactEditModal({ artifact, onSave, onClose }: ArtifactEditModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const [, setVisible] = useState(false);

  const user_id = useAuth().user?.id ?? '';

  const [contentText, setContentText] = useState<string>(
    typeof artifact.content === 'string'
      ? artifact.content
      : isPlainObject(artifact.content)
        ? JSON.stringify(artifact.content, null, 2)
        : ''
  );

  const [contextObj, setContextObj] = useState<JSONObject>(() => {
    if (typeof artifact.context === 'string') {
      try {
        const parsed = JSON.parse(artifact.context);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as JSONObject;
      } catch {
        // ignore
      }
    }
    if (isPlainObject(artifact.context)) return artifact.context as JSONObject;
    return { description: '', title: '', content_type: 'text/plain', tags: [] };
  });

  const { collections = [], isLoading: collectionsLoading } = useCollections();
  const initialTargetCollections = Array.isArray(artifact.committed_collection_ids)
    ? (artifact.committed_collection_ids as string[])
    : [];
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<string[]>(initialTargetCollections);

  const handleClose = useCallback(() => {
    setVisible(false);
    setTimeout(onClose, 150);
  }, [onClose]);

  useEffect(() => {
    setVisible(true);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && handleClose();
    const onClick = (e: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(e.target as Node)) handleClose();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onClick);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onClick);
    };
  }, [handleClose]);

  // Sync if a different artifact instance is passed in
  useEffect(() => {
    setContentText(
      typeof artifact.content === 'string'
        ? artifact.content
        : isPlainObject(artifact.content)
          ? JSON.stringify(artifact.content, null, 2)
          : ''
    );

    let next: JSONObject | null = null;
    if (typeof artifact.context === 'string') {
      try {
        const parsed = JSON.parse(artifact.context);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) next = parsed as JSONObject;
      } catch {
        // ignore
      }
    } else if (isPlainObject(artifact.context)) {
      next = artifact.context as JSONObject;
    }
    setContextObj(next ?? { description: '', title: '', content_type: 'text/plain', tags: [] });

    const nextTargets = Array.isArray(artifact.committed_collection_ids)
      ? (artifact.committed_collection_ids as string[])
      : [];
    setSelectedCollectionIds(nextTargets);
  }, [artifact, user_id]);


  const sameIds = (a?: Array<string | number>, b?: Array<string | number>) => {
    if (!Array.isArray(a) && !Array.isArray(b)) return true;
    if (!Array.isArray(a) || !Array.isArray(b)) return false;
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  };

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black bg-opacity-50"
      onClick={onClose}
      onMouseDown={(e) => e.stopPropagation()}
      onFocus={(e) => e.stopPropagation()}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
        onFocus={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-lg font-semibold">Edit Artifact</h2>
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={handleClose} 
            aria-label="Close"
          >
            <X size={18} />
          </Button>
        </div>

        {/* Tabs for Content/Context/Collections */}
        <Tabs defaultValue="content" className="flex-1 flex flex-col min-h-0">
          <TabsList className="mx-4 mt-4">
            <TabsTrigger value="content">Content</TabsTrigger>
            <TabsTrigger value="context">Context</TabsTrigger>
            <TabsTrigger value="collections">Collections</TabsTrigger>
          </TabsList>

          {/* Content Tab */}
          <TabsContent value="content" className="flex-1 overflow-y-auto p-4 mt-0">
            <textarea
              className="w-full border border-gray-300 rounded p-3 min-h-[400px] focus:outline-none focus:ring-2 focus:ring-blue-200 font-mono text-sm"
              value={contentText}
              onChange={(e) => setContentText(e.target.value)}
              placeholder="Enter artifact content..."
            />
          </TabsContent>

          {/* Context Tab */}
          <TabsContent value="context" className="flex-1 overflow-y-auto p-4 mt-0">
            <KeyValueEditor 
              key={String(artifact.id ?? 'draft')} 
              value={contextObj} 
              onChange={setContextObj}
              artifactId={artifact.id ? String(artifact.id) : undefined}
              filename={contextObj.filename as string}
            />
          </TabsContent>

          {/* Collections Tab */}
          <TabsContent value="collections" className="flex-1 overflow-y-auto p-4 mt-0">
            {collectionsLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-3/4" />
              </div>
            ) : (
              <div className="space-y-2">
                {collections.map(c => (
                  <label 
                    key={c.id} 
                    className="flex items-center gap-3 p-3 border rounded-lg hover:bg-gray-50 cursor-pointer transition"
                  >
                    <input
                      type="checkbox"
                      checked={selectedCollectionIds.some(x => x === c.id)}
                      onChange={() =>
                        setSelectedCollectionIds(prev =>
                          prev.some(x => x === c.id) ? prev.filter(x => x !== c.id) : [...prev, c.id]
                        )
                      }
                      className="w-4 h-4"
                    />
                    <span className="text-sm font-medium">{c.name}</span>
                  </label>
                ))}
                {collections.length === 0 && (
                  <p className="text-sm text-gray-500 text-center py-8">No collections available</p>
                )}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Footer - fixed at bottom */}
        <div className="flex justify-end gap-2 p-4 border-t border-gray-200 flex-shrink-0">
          <Button variant="outline" onClick={handleClose}>
            Close
          </Button>

          <Button
            onClick={async () => {
              // Handle collection membership changes via edge operations
              const artifactResponse = artifact as ArtifactResponse;
              const currentIds = Array.isArray(artifactResponse.committed_collection_ids)
                ? (artifactResponse.committed_collection_ids as string[])
                : [];
              const collectionsChanged = !sameIds(currentIds, selectedCollectionIds);

              if (collectionsChanged && artifact.id) {
                const currentSet = new Set(currentIds);
                const nextSet = new Set(selectedCollectionIds);
                for (const id of nextSet) {
                  if (!currentSet.has(id)) {
                    await addArtifactToCollection(id, String(artifact.id));
                  }
                }
                for (const id of currentSet) {
                  if (!nextSet.has(id)) {
                    const rootId = String((artifact as { root_id?: string }).root_id ?? artifact.id);
                    await removeArtifactFromCollection(id, rootId);
                  }
                }
              }

              const payload: ArtifactUpdate = {
                ...artifact,
                context: JSON.stringify(contextObj),
                content: contentText,
              };

              onSave(payload);
            }}
          >
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}
