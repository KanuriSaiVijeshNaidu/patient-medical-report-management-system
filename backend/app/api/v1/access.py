from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import CreateShareGrantRequest, ShareGrantResponse

router = APIRouter()


@router.post(
    "/create-share",
    response_model=ShareGrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create expiring QR code / URL share grant"
)
def create_share_grant(payload: CreateShareGrantRequest):
    """Creates a time-bound, revocable sharing grant with cryptographic token."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Share grant creation endpoint ready. Awaiting database connection."
    )


@router.get(
    "/view/{token}",
    summary="Public zero-install viewer resolution for shared reports"
)
def view_shared_grant(token: str):
    """Resolves a valid unexpired share token to temporary report download URLs."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Share viewer endpoint ready. Awaiting database connection."
    )


@router.delete(
    "/revoke/{grant_id}",
    status_code=status.HTTP_200_OK,
    summary="Immediately revoke an active share grant"
)
def revoke_share_grant(grant_id: UUID):
    """Marks a grant as revoked, immediately terminating all external access."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Revocation endpoint ready. Awaiting database connection."
    )
