from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter()


class HospitalStaffLoginRequest(BaseModel):
    email: str
    password: str
    hospital_registration_number: str


@router.post(
    "/login",
    summary="Hospital staff authentication with organization verification"
)
def staff_login(payload: HospitalStaffLoginRequest):
    """Authenticates hospital staff and verifies active institutional membership."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Hospital staff authentication endpoint ready. Awaiting database connection."
    )
