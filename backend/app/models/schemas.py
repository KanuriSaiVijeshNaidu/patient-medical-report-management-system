from datetime import date, datetime
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# -----------------------------------------------------------------------------
# Patient Schemas
# -----------------------------------------------------------------------------
class PatientProfileBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    date_of_birth: date
    gender: Literal["male", "female", "other", "prefer_not_to_say"]
    blood_group: Optional[Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]] = None
    emergency_contact_phone: Optional[str] = None


class PatientProfileCreate(PatientProfileBase):
    """Payload to create profile once phone OTP authentication is verified."""
    pass


class PatientProfileUpdate(BaseModel):
    blood_group: Optional[Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]] = None
    emergency_contact_phone: Optional[str] = None


class PatientRegistrationRequest(PatientProfileBase):
    phone_e164: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$")
    masked_aadhaar_ref: Optional[str] = Field(None, pattern=r"^XXXX-XXXX-\d{4}$")


class PatientProfileResponse(PatientProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: str
    verification_status: str
    phone_masked: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    masked_aadhaar_ref: Optional[str] = None


class AccountRecoveryInitiateRequest(BaseModel):
    target_patient_id: str = Field(..., min_length=10, max_length=32, description="Existing Patient ID e.g. MED-2026-8K4F29")
    challenge_date_of_birth: date
    challenge_emergency_contact_phone: Optional[str] = None


class AccountRecoveryInitiateResponse(BaseModel):
    recovery_request_id: UUID
    target_patient_id: str
    status: str
    message: str


class AccountRecoveryVerifyRequest(BaseModel):
    recovery_request_id: UUID


class AccountRecoveryVerifyResponse(BaseModel):
    success: bool
    patient_id: str
    message: str


# -----------------------------------------------------------------------------
# Medical Report Schemas
# -----------------------------------------------------------------------------
ReportCategory = Literal[
    "blood_test", "xray", "ct_scan", "mri", "prescription", "discharge_summary", "other"
]


class ReportUploadRequest(BaseModel):
    patient_id: UUID
    title: str = Field(..., min_length=3, max_length=255)
    category: ReportCategory
    report_date: date
    file_name: str
    file_size_bytes: int = Field(..., gt=0, le=26214400) # Max 25MB
    mime_type: str
    file_checksum_sha256: str = Field(..., min_length=64, max_length=64)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReportUploadResponse(BaseModel):
    report_id: str
    upload_url: str
    expires_in_seconds: int


class MedicalReportResponse(BaseModel):
    id: UUID
    report_id: str
    patient_id: UUID
    hospital_id: Optional[UUID] = None
    upload_source: Literal["patient", "hospital"]
    title: str
    category: ReportCategory
    report_date: date
    file_size_bytes: int
    mime_type: str
    verification_status: str
    created_at: datetime
    signed_download_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# -----------------------------------------------------------------------------
# Access Share Schemas (QR & Web View)
# -----------------------------------------------------------------------------
class CreateShareGrantRequest(BaseModel):
    patient_id: UUID
    scope: Literal["all", "specific_reports"] = "all"
    report_ids: List[UUID] = Field(default_factory=list)
    expiry_hours: int = Field(default=2, ge=1, le=168) # 1 hour to 7 days
    max_uses: Optional[int] = Field(default=None, ge=1)


class ShareGrantResponse(BaseModel):
    grant_id: UUID
    share_url: str
    qr_payload_url: str
    expires_at: datetime


# -----------------------------------------------------------------------------
# Emergency Access Schemas
# -----------------------------------------------------------------------------
EmergencyReasonCategory = Literal[
    "unconscious_patient", "trauma_resuscitation", "acute_cardiac_arrest", "other_life_threatening"
]


class EmergencyAccessRequest(BaseModel):
    patient_id_code: str = Field(..., description="Unique Patient ID e.g. MED-2026-894102")
    reason_category: EmergencyReasonCategory
    clinical_justification: str = Field(..., min_length=20, max_length=2000)


class EmergencyAccessResponse(BaseModel):
    access_id: UUID
    patient_profile: PatientProfileResponse
    granted_at: datetime
    reports: List[MedicalReportResponse]
    warning: str = "This emergency access session has been permanently logged and submitted for clinical compliance audit."
