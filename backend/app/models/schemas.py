import re
from datetime import date, datetime
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator


# -----------------------------------------------------------------------------
# Patient Schemas
# -----------------------------------------------------------------------------
class PatientRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=8, max_length=128)
    gender: Literal["male", "female", "other", "prefer_not_to_say"]
    phone: str = Field(..., min_length=7, max_length=25)
    blood_group: Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    date_of_birth: Optional[date] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.-]+$", cleaned):
            raise ValueError("Username can only contain alphanumeric characters, underscores, hyphens, and periods.")
        if len(cleaned) < 3 or len(cleaned) > 30:
            raise ValueError("Username must be between 3 and 30 characters.")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"[0-9!@#$%^&*()_+\-=\[\]{};':\",.<>?/\\|]", v):
            raise ValueError("Password must contain at least one number or special character.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        digits = [c for c in v if c.isdigit()]
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError("Please provide a valid phone number with country code.")
        return v


class PatientRegisterResponse(BaseModel):
    patient_id: str
    full_name: str
    username: str
    access_token: str
    token_type: str = "bearer"
    message: str = "Registration successful"


class PatientLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def clean_username(cls, v: str) -> str:
        return v.strip().lower()


class PatientLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    patient_id: str
    username: str
    full_name: str


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
    metadata: Dict[str, Any] = Field(default_factory=dict)
    signed_download_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReportDownloadUrlResponse(BaseModel):
    report_id: str
    download_url: str
    expires_in_seconds: int


class ReportDeleteResponse(BaseModel):
    success: bool
    message: str
    report_id: str


# -----------------------------------------------------------------------------
# Access Share Schemas (QR & Web View)
# -----------------------------------------------------------------------------
class CreateReportShareRequest(BaseModel):
    report_id: Optional[str] = Field(
        default=None,
        description="Target medical report UUID or formatted report ID e.g. REP-2026-XXXXXX"
    )
    report_ids: Optional[List[str]] = Field(
        default=None,
        description="List of medical report UUIDs or formatted report IDs for multi-report sharing"
    )
    expires_in_seconds: Optional[int] = Field(
        default=900,
        ge=60,
        le=86400,
        description="Share duration in seconds (between 60s and 86400s / 24 hours, defaults to 900s / 15 minutes)"
    )


class ShareGrantResponse(BaseModel):
    grant_id: UUID
    report_id: str
    report_ids: List[str] = Field(default_factory=list)
    reports_count: int = 1
    share_url: str
    raw_token: str
    expires_at: datetime
    expires_in_seconds: int


class SharedReportItem(BaseModel):
    report_id: str
    title: str
    category: str
    report_date: date
    file_size_bytes: int
    mime_type: str
    verification_status: str
    download_url: str
    download_url_expires_in_seconds: int


class SharedReportViewResponse(BaseModel):
    grant_id: UUID
    report_id: str
    title: str
    category: str
    report_date: date
    file_size_bytes: int
    mime_type: str
    verification_status: str
    download_url: str
    download_url_expires_in_seconds: int
    share_expires_at: datetime
    reports: List[SharedReportItem] = Field(default_factory=list)


class RevokeShareResponse(BaseModel):
    success: bool
    message: str
    grant_id: UUID
    revoked_at: datetime


# -----------------------------------------------------------------------------
# Doctor Patient Lookup & Hospital Staff Schemas
# -----------------------------------------------------------------------------
class HospitalStaffLoginRequest(BaseModel):
    email: str
    password: str
    hospital_registration_number: Optional[str] = "HOSP-REG-4421"


class HospitalStaffLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    staff_id: UUID
    staff_name: str
    staff_role: str
    employee_id: str
    hospital_id: UUID
    hospital_name: str
    hospital_registration_number: str


class DoctorPatientInfo(BaseModel):
    patient_id: str
    full_name: str
    gender: str
    blood_group: Optional[str] = None
    date_of_birth: Optional[date] = None


class DoctorPatientLookupResponse(BaseModel):
    authorized: bool
    patient: DoctorPatientInfo
    hospital_name: str
    hospital_id: UUID
    reports: List[SharedReportItem] = Field(default_factory=list)


class GrantHospitalAccessRequest(BaseModel):
    hospital_registration_number: str = Field(..., description="Hospital registration number, e.g. HOSP-REG-4421")
    expires_in_days: Optional[int] = Field(default=30, ge=1, le=365)


class GrantHospitalAccessResponse(BaseModel):
    success: bool
    message: str
    hospital_name: str
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
