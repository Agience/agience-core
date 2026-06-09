// Tests for upload utility functions
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { uploadPart, uploadWithProgress, uploadMultipart } from '../upload';
import * as workspacesApi from '../../api/workspaces';

// Mock the API
vi.mock('../../api/workspaces', () => ({
  updateUploadStatus: vi.fn(),
  getMultipartPartUrl: vi.fn(),
}));

interface MockXHR {
  open: ReturnType<typeof vi.fn>;
  send: ReturnType<typeof vi.fn>;
  setRequestHeader: ReturnType<typeof vi.fn>;
  getResponseHeader: ReturnType<typeof vi.fn>;
  upload: {
    onprogress?: (e: ProgressEvent) => void;
  };
  status: number;
  onload: (() => void) | null;
  onerror: (() => void) | null;
}

describe('uploadPart', () => {
  let mockXHR: MockXHR;
  
  beforeEach(() => {
    mockXHR = {
      open: vi.fn(),
      send: vi.fn(),
      setRequestHeader: vi.fn(),
      getResponseHeader: vi.fn(),
      upload: {},
      status: 0,
      onload: null,
      onerror: null,
    };
    
    globalThis.XMLHttpRequest = vi.fn(function() {
      return mockXHR;
    }) as unknown as typeof XMLHttpRequest;
  });

  it('should upload a chunk successfully', async () => {
    const blob = new Blob(['test data']);
    const url = 'https://example.com/upload';
    const expectedETag = '"abc123"';
    
    mockXHR.getResponseHeader.mockReturnValue(expectedETag);
    mockXHR.status = 200;
    
    const promise = uploadPart(url, blob);
    
    // Simulate successful upload
    if (mockXHR.onload) mockXHR.onload();
    
    const result = await promise;
    
    expect(result).toBe('abc123'); // ETag with quotes removed
    expect(mockXHR.open).toHaveBeenCalledWith('PUT', url);
    expect(mockXHR.send).toHaveBeenCalledWith(blob);
  });

  it('should call progress callback during upload', async () => {
    const blob = new Blob(['test data']);
    const url = 'https://example.com/upload';
    const onProgress = vi.fn();
    
    mockXHR.getResponseHeader.mockReturnValue('"etag"');
    mockXHR.status = 200;
    
    const promise = uploadPart(url, blob, onProgress);
    
    // Simulate progress event
    mockXHR.upload.onprogress?.(new ProgressEvent('progress', {
      lengthComputable: true,
      loaded: 50,
      total: 100,
    }));
    
    // Complete upload
    if (mockXHR.onload) mockXHR.onload();
    await promise;
    
    expect(onProgress).toHaveBeenCalledWith(50, 100);
  });

  it('should reject on network error', async () => {
    const blob = new Blob(['test data']);
    const url = 'https://example.com/upload';
    
    const promise = uploadPart(url, blob);
    
    // Simulate network error
    if (mockXHR.onerror) mockXHR.onerror();
    
    await expect(promise).rejects.toThrow('PUT network error');
  });

  it('should reject on HTTP error status', async () => {
    const blob = new Blob(['test data']);
    const url = 'https://example.com/upload';
    
    mockXHR.status = 500;
    
    const promise = uploadPart(url, blob);
    
    // Simulate error response
    if (mockXHR.onload) mockXHR.onload();
    
    await expect(promise).rejects.toThrow('PUT 500');
  });

  it('should reject when ETag is missing', async () => {
    const blob = new Blob(['test data']);
    const url = 'https://example.com/upload';
    
    mockXHR.getResponseHeader.mockReturnValue(null);
    mockXHR.status = 200;
    
    const promise = uploadPart(url, blob);
    
    if (mockXHR.onload) mockXHR.onload();
    
    await expect(promise).rejects.toThrow('No ETag in response');
  });
});

describe('uploadWithProgress', () => {
  let mockXHR: MockXHR;
  
  beforeEach(() => {
    vi.useFakeTimers();
    mockXHR = {
      open: vi.fn(),
      send: vi.fn(),
      setRequestHeader: vi.fn(),
      getResponseHeader: vi.fn(),
      upload: {},
      status: 0,
      onload: null,
      onerror: null,
    };
    
    globalThis.XMLHttpRequest = vi.fn(function() {
      return mockXHR;
    }) as unknown as typeof XMLHttpRequest;
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should upload file with progress tracking', async () => {
    const file = new File(['test content'], 'test.txt', { type: 'text/plain' });
    const workspaceId = 'workspace-1';
    const uploadId = 'upload-1';
    const url = 'https://example.com/upload';
    const onProgress = vi.fn();
    
    vi.mocked(workspacesApi.updateUploadStatus).mockResolvedValue({
      id: uploadId,
      context: { upload: { status: 'uploading', progress: 0.5 } }
    } as never);
    mockXHR.status = 200;
    
    const promise = uploadWithProgress(workspaceId, uploadId, url, file, onProgress);
    
    // Simulate progress
    mockXHR.upload.onprogress?.(new ProgressEvent('progress', {
      lengthComputable: true,
      loaded: 50,
      total: 100,
    }));
    
    // Flush any scheduled progress/status work deterministically
    vi.advanceTimersByTime(20);
    await vi.runOnlyPendingTimersAsync();
    
    // Complete upload
    if (mockXHR.onload) mockXHR.onload();
    await promise;
    
    expect(onProgress).toHaveBeenCalledWith(0.5);
    expect(workspacesApi.updateUploadStatus).toHaveBeenCalledWith(
      workspaceId,
      uploadId,
      { status: 'uploading', progress: 0.5 }
    );
    expect(mockXHR.setRequestHeader).toHaveBeenCalledWith('Content-Type', 'text/plain');
    expect(mockXHR.setRequestHeader).toHaveBeenCalledWith('Cache-Control', 'private, max-age=31536000, immutable');
  });

  it('should handle upload without progress callback', async () => {
    const file = new File(['test'], 'test.txt');
    const workspaceId = 'workspace-1';
    const uploadId = 'upload-1';
    const url = 'https://example.com/upload';
    
    vi.mocked(workspacesApi.updateUploadStatus).mockResolvedValue({
      id: uploadId,
      context: { upload: { status: 'uploading', progress: 1.0 } }
    } as never);
    mockXHR.status = 201;
    
    const promise = uploadWithProgress(workspaceId, uploadId, url, file);
    
    // Simulate progress
    mockXHR.upload.onprogress?.(new ProgressEvent('progress', {
      lengthComputable: true,
      loaded: 100,
      total: 100,
    }));
    
    // Flush any scheduled progress/status work deterministically
    vi.advanceTimersByTime(20);
    await vi.runOnlyPendingTimersAsync();
    
    if (mockXHR.onload) mockXHR.onload();
    await promise;
    
    expect(workspacesApi.updateUploadStatus).toHaveBeenCalled();
  });

  it('should reject on upload failure', async () => {
    const file = new File(['test'], 'test.txt');
    const workspaceId = 'workspace-1';
    const uploadId = 'upload-1';
    const url = 'https://example.com/upload';
    
    mockXHR.status = 403;
    
    const promise = uploadWithProgress(workspaceId, uploadId, url, file);
    
    if (mockXHR.onload) mockXHR.onload();
    
    await expect(promise).rejects.toThrow('PUT 403');
  });
});

describe('uploadMultipart', () => {
  let mockXHR: MockXHR;
  
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockXHR = {
      open: vi.fn(),
      send: vi.fn(),
      setRequestHeader: vi.fn(),
      getResponseHeader: vi.fn(),
      upload: {},
      status: 200,
      onload: null,
      onerror: null,
    };
    
    globalThis.XMLHttpRequest = vi.fn(function() {
      return mockXHR;
    }) as unknown as typeof XMLHttpRequest;
    
    vi.mocked(workspacesApi.getMultipartPartUrl).mockResolvedValue({ 
      url: 'https://example.com/part' 
    } as never);
    vi.mocked(workspacesApi.updateUploadStatus).mockResolvedValue({
      id: 'upload-1',
      context: { upload: { status: 'complete' } }
    } as never);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should upload file in multiple parts', async () => {
    const largeContent = 'x'.repeat(25 * 1024 * 1024); // 25MB (3 parts of 10MB each)
    const file = new File([largeContent], 'large.txt', { type: 'text/plain' });
    const workspaceId = 'workspace-1';
    const uploadId = 'upload-1';
    const onProgress = vi.fn();
    
    mockXHR.getResponseHeader.mockReturnValue('"etag123"');
    
    // Set up send to trigger onload BEFORE starting the upload
    mockXHR.send = vi.fn(() => {
      // Simulate immediate success for each part
      setTimeout(() => {
        if (mockXHR.onload) mockXHR.onload();
      }, 0);
    });

    const promise = uploadMultipart(workspaceId, uploadId, file, onProgress);

    await vi.runAllTimersAsync();
    await promise;
    
    // Should request 3 parts (25MB / 10MB = 3 parts)
    expect(workspacesApi.getMultipartPartUrl).toHaveBeenCalledTimes(3);
    expect(workspacesApi.getMultipartPartUrl).toHaveBeenCalledWith(workspaceId, uploadId, 1);
    expect(workspacesApi.getMultipartPartUrl).toHaveBeenCalledWith(workspaceId, uploadId, 2);
    expect(workspacesApi.getMultipartPartUrl).toHaveBeenCalledWith(workspaceId, uploadId, 3);
    
    // Should complete the multipart upload
    expect(workspacesApi.updateUploadStatus).toHaveBeenCalledWith(
      workspaceId,
      uploadId,
      expect.objectContaining({
        status: 'complete',
        parts: expect.arrayContaining([
          { part_number: 1, etag: 'etag123' },
          { part_number: 2, etag: 'etag123' },
          { part_number: 3, etag: 'etag123' },
        ])
      })
    );
  });

  it('should call progress callback during multipart upload', async () => {
    const content = 'x'.repeat(15 * 1024 * 1024); // 15MB (2 parts)
    const file = new File([content], 'file.txt');
    const workspaceId = 'workspace-1';
    const uploadId = 'upload-1';
    const onProgress = vi.fn();
    
    mockXHR.getResponseHeader.mockReturnValue('"etag"');
    
    // Track progress events
    let progressHandler: ((e: ProgressEvent) => void) | null = null;
    
    mockXHR.send = vi.fn(() => {
      // Simulate progress during upload
      if (mockXHR.upload.onprogress) {
        progressHandler = mockXHR.upload.onprogress;
        setTimeout(() => {
          if (progressHandler) {
            progressHandler(new ProgressEvent('progress', {
              lengthComputable: true,
              loaded: 5 * 1024 * 1024,
              total: 10 * 1024 * 1024,
            }));
          }
          if (mockXHR.onload) mockXHR.onload();
        }, 10);
      } else {
        setTimeout(() => {
          if (mockXHR.onload) mockXHR.onload();
        }, 0);
      }
    });
    
    const promise = uploadMultipart(workspaceId, uploadId, file, onProgress);

    await vi.runAllTimersAsync();
    await promise;
    
    expect(onProgress).toHaveBeenCalled();
  });
});
