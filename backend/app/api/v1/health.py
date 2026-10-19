from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health_check():
    """Health check endpoint indicating service liveness and current configuration state."""
    return {
        "status": "healthy",
        "service": "Patient Medical Report Management API",
        "environment": settings.ENVIRONMENT,
        "supabase_connected": bool(settings.SUPABASE_URL and settings.SUPABASE_KEY),
    }
