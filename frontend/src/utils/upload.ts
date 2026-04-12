// Upload utility functions for file handling

import { updateUploadStatus, getMultipartPartUrl } from '../api/workspaces';

/**
 * Upload single part with progress tracking
 */
export async function uploadPart(
  url: string,
  chunk: Blob,
  onProgress?: (loaded: number, total: number) => void
): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(e.loaded, e.total);
        }
      };
    }
    
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const etag = xhr.getResponseHeader("ETag");
        if (!etag) {
          reject(new Error("No ETag in response"));
        } else {
          resolve(etag.replace(/"/g, "")); // Remove quotes from ETag
        }
      } else {
        reject(new Error(`PUT ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("PUT network error"));
    xhr.send(chunk);
  });
}

/**
 * Upload with progress tracking (single PUT)
 */
export async function uploadWithProgress(
  workspaceId: string,
  uploadId: string,
  url: string,
  file: File,
  onProgress?: (progress: number) => void
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.setRequestHeader("Cache-Control", "private, max-age=31536000, immutable");
    
    // Send progress updates to backend
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const progress = e.loaded / e.total;
        
        // Notify callback for local UI updates
        onProgress?.(progress);
        
        // Also send to backend (fire and forget)
        updateUploadStatus(workspaceId, uploadId, {
          status: "uploading",
          progress: progress,
        }).catch(() => {/* ignore progress update failures */});
      }
    };
    
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`PUT ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("PUT network error"));
    xhr.send(file);
  });
}

/**
 * Multipart upload with progress tracking
 */
export async function uploadMultipart(
  workspaceId: string,
  uploadId: string,
  file: File,
  onProgress?: (progress: number) => void
): Promise<void> {
  const PART_SIZE = 10 * 1024 * 1024; // 10MB parts (min is 5MB except last part)
  const totalParts = Math.ceil(file.size / PART_SIZE);
  const parts: Array<{ PartNumber: number; ETag: string }> = [];
  let uploadedBytes = 0;
  
  for (let partNumber = 1; partNumber <= totalParts; partNumber++) {
    const start = (partNumber - 1) * PART_SIZE;
    const end = Math.min(start + PART_SIZE, file.size);
    const chunk = file.slice(start, end);

    // Get presigned URL for this part
    const { url } = await getMultipartPartUrl(workspaceId, uploadId, partNumber);

    // Upload the part
    const etag = await uploadPart(url, chunk, (loaded) => {
      // Calculate overall progress
      const currentPartBytes = uploadedBytes + loaded;
      const progress = currentPartBytes / file.size;
      
      // Notify callback for local UI updates
      onProgress?.(progress);
      
      // Send to backend (fire and forget)
      updateUploadStatus(workspaceId, uploadId, {
        status: "uploading",
        progress: progress,
      }).catch(() => {});
    });
    
    parts.push({ PartNumber: partNumber, ETag: etag });
    uploadedBytes += chunk.size;
  }
  
  // Complete the multipart upload
  await updateUploadStatus(workspaceId, uploadId, {
    status: "complete",
    parts: parts.map(p => ({
      part_number: p.PartNumber,
      etag: p.ETag,
    })),
  });
}
