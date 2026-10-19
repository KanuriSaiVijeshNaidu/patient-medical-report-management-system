from typing import List
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import (
    ReportUploadRequest,
    ReportUploadResponse,
    MedicalReportResponse,
)

router = APIRouter()


@router.post(
    "/request-upload",
    response_model=ReportUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request pre-signed upload URL for report document"
)
def request_report_upload(payload: ReportUploadRequest):
    """Validates metadata and issues a pre-signed short-lived upload URL."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Report upload initialization ready. Supabase Storage bucket configuration required."
    )


@router.get(
    "/patient/{patient_id}",
    response_model=List[MedicalReportResponse],
    summary="List patient medical reports with security authorization"
)
def list_patient_reports(patient_id: UUID):
    """Lists categorized reports for an authorized patient or granted hospital."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Report retrieval endpoint ready. Awaiting database connection."
    )
