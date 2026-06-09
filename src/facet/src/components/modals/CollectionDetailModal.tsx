import { toast } from 'sonner';
import { useState, useEffect, useCallback } from 'react';
import { Eye, EyeOff, Copy } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { CollectionResponse, Grant, CollectionCommitResponse } from '../../api/types';
import { useAuth } from '../../hooks/useAuth';
import {
  listCollections,
  createCollection,
  updateCollection,
  deleteCollection,
  listGrants,
  listCollectionCommits,
  createGrant,
  updateGrant,
  deleteGrant,
} from '../../api/collections';
import { formatProvenanceLabel } from '@/utils/provenance';

interface NewCollectionInput {
  name: string;
  description: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CollectionDetailModal({ open, onClose }: Props) {
  const user = useAuth()?.user;
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [newCollection, setNewCollection] = useState<NewCollectionInput>({ name: '', description: '' });
  const [editCollection, setEditCollection] = useState<NewCollectionInput>({ name: '', description: '' });
  const [collections, setCollections] = useState<CollectionResponse[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showGrantModal, setShowGrantModal] = useState(false);
  const [editingGrant, setEditingGrant] = useState<Grant | null>(null);
  const [grantName, setGrantName] = useState('');
  const [showGrantDeleteConfirm, setShowGrantDeleteConfirm] = useState(false);
  const [grantToDelete, setGrantToDelete] = useState<Grant | null>(null);
  const [commits, setCommits] = useState<CollectionCommitResponse[]>([]);
  const [visibleGrantKeys, setVisibleGrantKeys] = useState<Record<string, boolean>>({});
  const [read, setRead] = useState(true);
  const [write, setWrite] = useState(true);
  const [readRequiresIdentity, setReadRequiresIdentity] = useState(true);
  const [writeRequiresIdentity, setWriteRequiresIdentity] = useState(true);

  const selectedCollectionData = collections.find(c => c.id === selectedCollection) || null;
  const collectionCreatedBy = selectedCollectionData?.created_by;
  const isOwner = collectionCreatedBy === user?.id;
  const isPlatformOwned = !!(collectionCreatedBy && user?.platform_user_id && collectionCreatedBy === user.platform_user_id);

  const fetchCollections = useCallback(async () => {
    try {
      const data = await listCollections();
      setCollections(data);

      let collectionToUse = selectedCollection;
      if (data.length > 0 && !selectedCollection) {
        collectionToUse = data[0].id;
        setSelectedCollection(collectionToUse);
      }

      if (collectionToUse) {
        const [grantsData, commitData] = await Promise.all([
          listGrants(collectionToUse),
          listCollectionCommits(collectionToUse),
        ]);
        setGrants(grantsData);
        setCommits(commitData);
        const selected = data.find(c => c.id === collectionToUse);
        if (selected) {
          setEditCollection({ name: selected.name, description: selected.description || '' });
        }
      } else {
        setGrants([]);
        setCommits([]);
        setEditCollection({ name: '', description: '' });
      }
    } catch (err) {
      console.error('Failed to fetch collections or grants:', err);
    }
  }, [selectedCollection]);


  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  useEffect(() => {
    if (open) fetchCollections();
  }, [fetchCollections, open]);

  const handleCreateCollection = async () => {
    try {
      const created = await createCollection({
        name: newCollection.name,
        description: newCollection.description || ''
      });
      if (created.id) {
        fetchCollections();
        setShowCreateModal(false);
        setNewCollection({ name: '', description: '' });
      }
    } catch (err) {
      console.error('Failed to create collection:', err);
      toast.error('Failed to create collection');
    }
  };


  useEffect(() => {
    if (editingGrant && selectedCollection) {
      setGrantName(editingGrant.name || '');
      setRead(editingGrant.can_read);
      setWrite(editingGrant.can_update);
      setReadRequiresIdentity(editingGrant.read_requires_identity ?? editingGrant.requires_identity);
      setWriteRequiresIdentity(editingGrant.write_requires_identity ?? editingGrant.requires_identity);
    } else {
      setGrantName('');
      setRead(true);
      setWrite(true);
      setReadRequiresIdentity(true);
      setWriteRequiresIdentity(true);
    }
  }, [editingGrant, selectedCollection]);

  const handleUpdateCollection = async () => {
    if (!selectedCollection || !selectedCollectionData) return;
    if (!isOwner) return;
    try {
      await updateCollection(selectedCollection, editCollection);
      fetchCollections();
      toast.success('Collection updated successfully');
    } catch (err) {
      console.error('Failed to update collection:', err);
      toast.error('Failed to update collection');
    }
  };


  const handleDeleteCollection = async () => {
    if (!selectedCollection || !isOwner) return;
    try {
      await deleteCollection(selectedCollection);
      setSelectedCollection(null);
      fetchCollections();
      toast.success('Collection deleted');
    } catch (err) {
      console.error('Failed to delete collection:', err);
      toast.error('Failed to delete collection');
    }
  };


  const handleRemoveGrant = async (grantId: string) => {
    try {
      await deleteGrant(grantId);
      setGrants(prev => prev.filter(s => s.id !== grantId));
      toast.success('Grant removed');
    } catch (err) {
      console.error('Failed to remove grant:', err);
      toast.error('Failed to remove grant');
    }
  };


  const toggleKeyVisibility = (grantId: string) => {
    setVisibleGrantKeys(prev => ({ ...prev, [grantId]: !prev[grantId] }));
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center">
      <div className="relative bg-white rounded-xl shadow-2xl max-h-[90vh] min-w-[60vw] max-w-[90vw] overflow-hidden">
        <Button variant="ghost" size="icon" onClick={onClose} className="absolute top-4 right-4 z-10">✕</Button>
        <div className="p-4">
          <div className="container mx-auto py-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Sidebar */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-200">
                <div className="bg-gray-50 px-4 py-3 flex justify-between items-center rounded-t-xl border-b border-gray-200">
                  <h2 className="font-semibold text-gray-900">My Collections</h2>
                  <div className="flex space-x-2">
                    <Button
                      onClick={() => setShowCreateModal(true)}
                      disabled={!user}
                    >
                      New
                    </Button>
                  </div>
                </div>
                <div className="divide-y">
                  {collections.map(collection => {
                    return (
                      <Button
                        key={collection.id}
                        variant="ghost"
                        onClick={() => setSelectedCollection(collection.id)}
                        className={`w-full justify-start p-4 rounded-none h-auto ${selectedCollection === collection.id
                          ? 'bg-blue-50 border-l-4 border-blue-500'
                          : 'border-l-4 border-transparent'
                          }`}
                      >
                        <div className="font-medium text-gray-900 flex items-center gap-1.5">
                          {collection.name}
                          {user?.platform_user_id && collection.created_by === user.platform_user_id && (
                            <Badge className="border-0 bg-violet-100 text-violet-700 text-[10px] px-1 py-0 font-medium leading-none">
                              Platform
                            </Badge>
                          )}
                        </div>
                      </Button>
                    );
                  })}
                </div>
              </div>
              {/* Main content */}
              <div className="md:col-span-2">
                {selectedCollectionData ? (
                  <>
                    {/* Edit Collection */}
                    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                      <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          <h2 className="font-semibold text-gray-900">Details for {selectedCollectionData.name}</h2>
                          {isPlatformOwned && (
                            <Badge className="border-0 bg-violet-100 text-violet-700 text-[10px] px-1.5 py-0.5 font-medium">
                              Platform
                            </Badge>
                          )}
                        </div>
                        <Button
                          variant="destructive"
                          onClick={() => setShowDeleteConfirm(true)}
                          disabled={!isOwner}
                        >
                          Delete
                        </Button>
                      </div>
                      <div className="p-6 space-y-4">
                        <input
                          type="text"
                          placeholder="Name"
                          value={editCollection.name}
                          onChange={e => setEditCollection(prev => ({ ...prev, name: e.target.value }))}
                          className="w-full border rounded px-3 py-2"
                          disabled={!isOwner}
                        />
                        <input
                          type="text"
                          placeholder="Description"
                          value={editCollection.description}
                          onChange={e => setEditCollection(prev => ({ ...prev, description: e.target.value }))}
                          className="w-full border rounded px-3 py-2"
                          disabled={!isOwner}
                        />
                        <div className="flex space-x-3">
                          <Button
                            onClick={handleUpdateCollection}
                            disabled={!isOwner}
                          >
                            Update
                          </Button>
                        </div>
                      </div>
                    </div>
                    {/* Grants */}
                    <div className="mt-10 w-full bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                      <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
                        <h2 className="font-semibold text-gray-900">Grants for {selectedCollectionData.name}</h2>
                        <Button
                          onClick={() => {
                            setEditingGrant(null);
                            setShowGrantModal(true);
                          }}
                          disabled={!isOwner}
                        >
                          New
                        </Button>
                      </div>
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Name</TableHead>
                              <TableHead>Permissions</TableHead>
                              <TableHead>Key</TableHead>
                              <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {grants.length > 0 ? (
                              grants.map((grant) => (
                                <TableRow key={grant.id}>
                                  <TableCell className="font-medium">{grant.name}</TableCell>
                                  <TableCell>
                                    {[
                                      grant.can_read
                                        ? grant.read_requires_identity ?? grant.requires_identity
                                          ? 'Read (Identified)'
                                          : 'Read (Unidentified)'
                                        : null,
                                      grant.can_update
                                        ? grant.write_requires_identity ?? grant.requires_identity
                                          ? 'Write (Identified)'
                                          : 'Write (Unidentified)'
                                        : null,
                                    ]
                                      .filter(Boolean)
                                      .join(', ')}
                                  </TableCell>
                                  <TableCell>
                                    <div className="flex items-center space-x-2">
                                      <code className="text-xs bg-gray-100 px-2 py-1 rounded">
                                        {visibleGrantKeys[grant.id] ? grant.claim_token || '' : '••••••••••••'}
                                      </code>
                                      <Button 
                                        variant="ghost" 
                                        size="icon" 
                                        onClick={() => toggleKeyVisibility(grant.id)} 
                                        className="h-7 w-7"
                                      >
                                        {visibleGrantKeys[grant.id] ? <EyeOff size={14} /> : <Eye size={14} />}
                                      </Button>
                                      <Button 
                                        variant="ghost" 
                                        size="icon" 
                                        onClick={() => {
                                          navigator.clipboard.writeText(grant.claim_token || '');
                                          toast.success('Copied');
                                        }} 
                                        className="h-7 w-7"
                                      >
                                        <Copy size={14} />
                                      </Button>
                                    </div>
                                  </TableCell>
                                  <TableCell className="text-right">
                                    <div className="flex justify-end space-x-2">
                                      <Button
                                        variant="link"
                                        size="sm"
                                        onClick={() => {
                                          setEditingGrant(grant);
                                          setShowGrantModal(true);
                                        }}
                                        disabled={!isOwner}
                                        className="h-auto p-0"
                                      >
                                        Edit
                                      </Button>
                                      <Button
                                        variant="link"
                                        size="sm"
                                        onClick={() => {
                                          setGrantToDelete(grant);
                                          setShowGrantDeleteConfirm(true);
                                        }}
                                        disabled={!isOwner}
                                        className="text-red-500 hover:text-red-600 h-auto p-0"
                                      >
                                        Delete
                                      </Button>
                                    </div>
                                  </TableCell>
                                </TableRow>
                              ))
                            ) : (
                              <TableRow>
                                <TableCell colSpan={4} className="text-center py-8 text-gray-500">
                                  No grants created yet.
                                </TableCell>
                              </TableRow>
                            )}
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                    {/* Commit History */}
                    <div className="mt-10 w-full bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                      <div className="p-4 border-b bg-gray-50">
                        <h2 className="font-semibold text-gray-900">Commit History</h2>
                      </div>
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Time</TableHead>
                              <TableHead>Message</TableHead>
                              <TableHead>Actor</TableHead>
                              <TableHead>Provenance</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {commits.length > 0 ? (
                              commits.map((commit) => {
                                const actor = commit.presenter_id || commit.author_id;
                                const provenance = `${formatProvenanceLabel(commit.confirmation)} / ${formatProvenanceLabel(commit.changeset_type)}`;
                                return (
                                  <TableRow key={commit.id}>
                                    <TableCell className="text-xs text-gray-600 whitespace-nowrap">
                                      {commit.timestamp ? new Date(commit.timestamp).toLocaleString() : 'Unknown'}
                                    </TableCell>
                                    <TableCell className="font-medium">{commit.message || 'No message'}</TableCell>
                                    <TableCell className="text-xs text-gray-700">{actor}</TableCell>
                                    <TableCell className="text-xs text-gray-700">{provenance}</TableCell>
                                  </TableRow>
                                );
                              })
                            ) : (
                              <TableRow>
                                <TableCell colSpan={4} className="text-center py-8 text-gray-500">
                                  No commits recorded yet.
                                </TableCell>
                              </TableRow>
                            )}
                          </TableBody>
                        </Table>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-8 text-center">
                    <p className="text-gray-600">You have no collections. Create one now!</p>
                  </div>
                )}
              </div>
            </div>
          </div>
          {/* Grant Modal (Create/Edit) */}
          <Dialog open={showGrantModal} onOpenChange={(open) => {
            setShowGrantModal(open);
            if (!open) {
              setEditingGrant(null);
              setGrantName('');
            }
          }}>
            <DialogContent className="sm:max-w-[500px]">
              <DialogHeader>
                <DialogTitle>{editingGrant ? 'Edit Grant' : 'New Grant'}</DialogTitle>
                <DialogDescription>
                  {editingGrant 
                    ? 'Update grant permissions and settings.'
                    : 'Create a new grant key to provide access to this collection.'}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6">
                <div className="space-y-2">
                  <label className="text-sm font-medium leading-none">Name</label>
                  <input
                    type="text"
                    placeholder="Enter grant name"
                    value={grantName}
                    onChange={e => setGrantName(e.target.value)}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!isOwner}
                  />
                </div>
                <div className="space-y-4">
                  <label className="text-sm font-medium leading-none">Permissions</label>
                  <div className="grid grid-cols-2 gap-4">
                    <label className="flex items-center space-x-2 text-sm">
                      <input
                        type="checkbox"
                        checked={read}
                        onChange={() => setRead(!read)}
                        className="h-4 w-4 rounded border-gray-300"
                        disabled={!isOwner}
                      />
                      <span>Read Access</span>
                    </label>
                    <label className="flex items-center space-x-2 text-sm">
                      <input
                        type="checkbox"
                        checked={write}
                        onChange={() => setWrite(!write)}
                        className="h-4 w-4 rounded border-gray-300"
                        disabled={!isOwner}
                      />
                      <span>Write Access</span>
                    </label>
                    <label className="flex items-center space-x-2 text-sm text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={readRequiresIdentity}
                        onChange={() => setReadRequiresIdentity(!readRequiresIdentity)}
                        className="h-4 w-4 rounded border-gray-300"
                        disabled={!isOwner || !read}
                      />
                      <span>Require Identity (Read)</span>
                    </label>
                    <label className="flex items-center space-x-2 text-sm text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={writeRequiresIdentity}
                        onChange={() => setWriteRequiresIdentity(!writeRequiresIdentity)}
                        className="h-4 w-4 rounded border-gray-300"
                        disabled={!isOwner || !write}
                      />
                      <span>Require Identity (Write)</span>
                    </label>
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowGrantModal(false);
                    setEditingGrant(null);
                    setGrantName('');
                  }}
                >
                  Cancel
                </Button>
                <Button
                  onClick={async () => {
                    if (!selectedCollection) return;
                    if (!grantName.trim()) {
                      toast.error('Name is required');
                      return;
                    }
                    const basePayload = {
                      name: grantName.trim(),
                      can_read: read,
                      can_update: write,
                    };
                    try {
                      let updatedGrant: Grant;
                      if (editingGrant) {
                        updatedGrant = await updateGrant(editingGrant.id, basePayload);
                        setGrants(prev =>
                          prev.map(s => (s.id === editingGrant.id ? { ...updatedGrant, claim_token: s.claim_token } : s))
                        );
                      } else {
                        updatedGrant = await createGrant(selectedCollection, { ...basePayload, requires_identity: readRequiresIdentity });
                        setGrants(prev => [...prev, { ...updatedGrant, claim_token: updatedGrant.claim_token || undefined }]);
                      }
                      setShowGrantModal(false);
                      setEditingGrant(null);
                      setGrantName('');
                      toast.success(editingGrant ? 'Grant updated' : 'Grant created');
                    } catch (err) {
                      console.error('Failed to create/edit grant:', err);
                      toast.error('Failed to save grant');
                    }
                  }}
                  disabled={!isOwner}
                >
                  {editingGrant ? 'Save' : 'Create'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          {/* Create Collection Modal */}
          <Dialog open={showCreateModal} onOpenChange={(open) => {
            setShowCreateModal(open);
            if (!open) setNewCollection({ name: '', description: '' });
          }}>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle>New Collection</DialogTitle>
                <DialogDescription>
                  Create a new collection to organize and share your knowledge artifacts.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium leading-none">Name</label>
                  <input
                    type="text"
                    placeholder="Enter collection name"
                    value={newCollection.name}
                    onChange={(e) => setNewCollection(prev => ({ ...prev, name: e.target.value }))}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium leading-none">Description</label>
                  <input
                    type="text"
                    placeholder="Optional description"
                    value={newCollection.description}
                    onChange={(e) => setNewCollection(prev => ({ ...prev, description: e.target.value }))}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowCreateModal(false);
                    setNewCollection({ name: '', description: '' });
                  }}
                >
                  Cancel
                </Button>
                <Button
                  disabled={!newCollection.name.trim()}
                  onClick={handleCreateCollection}
                >
                  Create
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          {/* Delete Collection Confirmation */}
          <Dialog open={showDeleteConfirm && !!selectedCollectionData} onOpenChange={setShowDeleteConfirm}>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle className="text-red-600">Delete Collection</DialogTitle>
                <DialogDescription>
                  Are you sure you want to delete this collection? This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowDeleteConfirm(false)}>
                  Cancel
                </Button>
                <Button 
                  variant="destructive" 
                  onClick={async () => { 
                    await handleDeleteCollection(); 
                    setShowDeleteConfirm(false); 
                  }} 
                  disabled={!isOwner}
                >
                  Delete
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          {/* Delete Grant Confirmation */}
          <Dialog open={showGrantDeleteConfirm && !!grantToDelete} onOpenChange={(open) => {
            setShowGrantDeleteConfirm(open);
            if (!open) setGrantToDelete(null);
          }}>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle className="text-red-600">Revoke Grant</DialogTitle>
                <DialogDescription>
                  Are you sure you want to revoke this grant? This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button 
                  variant="outline" 
                  onClick={() => { 
                    setGrantToDelete(null); 
                    setShowGrantDeleteConfirm(false); 
                  }}
                >
                  Cancel
                </Button>
                <Button 
                  variant="destructive" 
                  onClick={async () => { 
                    if (grantToDelete) await handleRemoveGrant(grantToDelete.id); 
                    setGrantToDelete(null); 
                    setShowGrantDeleteConfirm(false); 
                  }} 
                  disabled={!isOwner}
                >
                  Delete
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </div>
  );
}
