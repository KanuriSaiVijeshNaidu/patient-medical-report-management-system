from fastapi import APIRouter
from app.core.config import settings
from app.core.database import check_supabase_connection

router = APIRouter()


@router.get("/health")
def health_check():
    """Health check endpoint indicating service liveness and current configuration state."""
    return {
        "status": "healthy",
        "service": "Patient Medical Report Management API",
        "environment": settings.ENVIRONMENT,
        "supabase_connected": check_supabase_connection(),
    }
