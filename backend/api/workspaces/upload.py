# schemas/api/workspaces/upload.py
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class UploadInitiateRequest(BaseModel):
    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="Content type of the file")
    size: int = Field(..., ge=0, description="File size in bytes")
    order_key: Optional[str] = Field(None, description="Fractional index key for artifact ordering")
    context: Optional[dict] = Field(None, description="Additional context metadata")


class UploadInitiateResponse(BaseModel):
    upload_id: str = Field(..., description="Artifact ID to use for upload tracking")
    mode: str = Field(..., description="Upload mode: 'put' or 'multipart'")
    key: str = Field(..., description="S3 object key (internal use)")
    url: Optional[str] = Field(None, description="Presigned PUT URL (mode=put only)")
    uploadId: Optional[str] = Field(None, description="Multipart upload ID (mode=multipart only)")
    artifact: dict = Field(..., description="The created artifact object")
    # Note: public_url removed - files are accessed via signed URLs from /artifacts/{id}/content-url endpoint


class UploadStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Upload status: 'uploading', 'complete', or 'failed'")
    progress: Optional[float] = Field(None, ge=0.0, le=1.0, description="Upload progress (0.0-1.0)")
    parts: Optional[List[Dict]] = Field(None, description="Completed multipart upload parts")
    context_patch: Optional[Dict] = Field(None, description="Additional context fields to merge")


class MultipartPartUrlRequest(BaseModel):
    part_number: int = Field(..., ge=1, le=10000, description="Part number (1-10000)")
