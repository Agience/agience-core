// utils/artifactAdapter.ts
import { v4 as uuidv4 } from 'uuid';
import { Artifact } from '../context/workspace/workspace.types';


// Define a union of supported input types
type ArtifactInput = File | string; // Extend with more types as needed

export function toArtifact(input: ArtifactInput, _userId: string = ''): Artifact {
  const id = `${getPrefix(input)}-${uuidv4()}`;

  if (input instanceof File) {
    return {
      id,
      context: input.name,
      content: JSON.stringify({
        uri: `workspace://${id}`,
        size: input.size,
        modified: new Date(input.lastModified).toISOString(),
        type: input.type || 'unknown',
        name: input.name
      }, null, 2),
      state: 'draft',
    };
  }

  if (typeof input === 'string') {
    return {
      id,
      context: input,
      content: JSON.stringify({
        uri: input,
        fetchedAt: new Date().toISOString(),
      }, null, 2),
      state: 'draft',
    };
  }

  throw new Error('Unsupported input type for toArtifact');
}

// Helper to prefix ID based on input type
function getPrefix(input: ArtifactInput): string {
  if (input instanceof File) return 'file';
  if (typeof input === 'string') return 'url';
  return 'unknown';
}
