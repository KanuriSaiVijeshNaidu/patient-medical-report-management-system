from fastapi import APIRouter
from app.api.v1 import health, patients, reports, access, emergency, hospital

api_router = APIRouter(prefix="/v1")

# Core endpoints
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(patients.router, prefix="/patients", tags=["Patients"])
api_router.include_router(reports.router, prefix="/reports", tags=["Medical Reports"])
api_router.include_router(access.router, prefix="/access", tags=["Record Access & Sharing"])
api_router.include_router(emergency.router, prefix="/emergency", tags=["Emergency Access"])
api_router.include_router(hospital.router, prefix="/hospital", tags=["Hospital Operations"])
