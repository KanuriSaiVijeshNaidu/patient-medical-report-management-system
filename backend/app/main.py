from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import api_router

app = FastAPI(
    title="Patient Medical Report Management System API",
    description="Secure, patient-centric REST API for managing, organizing, and sharing medical reports.",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(api_router, prefix="/api")


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to Patient Medical Report Management System API",
        "documentation": "/docs" if settings.DEBUG else "Disabled in production",
        "health_check": "/api/v1/health",
    }
