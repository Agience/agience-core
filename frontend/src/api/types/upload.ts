// src/api/types/upload.ts

export interface UploadInitiateRequest {
  filename: string;
  content_type: string;
  size: number;
  order_key?: string; // Fractional index key for artifact ordering
  context?: Record<string, unknown>;
}

export interface UploadInitiateResponse {
  upload_id: string; // Artifact ID
  mode: "inline" | "put" | "multipart";
  url?: string; // Presigned PUT URL (for mode=put)
  uploadId?: string; // Multipart upload ID (for mode=multipart) - matches backend field name
  key: string; // S3 key (internal use)
  artifact: Record<string, unknown>; // The created artifact object
  // Note: public_url removed - use GET /artifacts/{artifact_id}/content-url for signed URLs
}

export interface UploadStatusUpdateRequest {
  status: "uploading" | "complete" | "failed";
  progress?: number;
  parts?: Array<{ part_number: number; etag: string }>;
  context_patch?: Record<string, unknown>;
}
