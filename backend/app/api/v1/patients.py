from fastapi import APIRouter, HTTPException, status
from app.models.schemas import PatientRegistrationRequest, PatientProfileResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=PatientProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient profile (Stub)"
)
def register_patient(payload: PatientRegistrationRequest):
    """Initiates patient registration and assigns unique Patient ID.
    (Full implementation pending database connectivity and OTP provider setup).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Patient registration service is initialized. Database and OTP provider configuration required."
    )


@router.get(
    "/lookup/{patient_id_code}",
    response_model=PatientProfileResponse,
    summary="Lookup patient profile by Patient ID (Stub)"
)
def lookup_patient(patient_id_code: str):
    """Searches patient profile by human-readable Patient ID code."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Patient lookup endpoint is initialized. Requires active staff session and DB configuration."
    )
