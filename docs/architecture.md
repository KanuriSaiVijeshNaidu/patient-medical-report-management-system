# System Architecture Document
## Patient Medical Report Management System

**Version:** 1.0.0-draft  
**Last Updated:** October 2026  

---

## 1. Architectural Overview

The system employs a decoupled, multi-tiered architecture with a Next.js frontend, a FastAPI Python backend service, and a managed Supabase infrastructure providing PostgreSQL with Row-Level Security (RLS) and encrypted object storage.

```mermaid
flowchart TD
    subgraph Clients["Client Layer"]
        A[Patient Mobile/Web App\nNext.js Portal]
        B[Hospital Staff Workstation\nNext.js Hospital Portal]
        C[Non-Integrated Provider Browser\nZero-Install Viewer]
        D[Admin Operations Console\nNext.js Admin Portal]
    end

    subgraph Edge["Gateway & CDN"]
        GW[Edge Routing & TLS 1.3 Termination]
    end

    subgraph BackendApp["Application Backend Layer (FastAPI)"]
        API[FastAPI REST API Service]
        AuthGuard[Auth & RBAC Middleware]
        RateLimiter[Rate Limiter & Gateway Guard]
        AuditSvc[Audit & Compliance Service]
        StorageSvc[Storage Signed URL Generator]
        ShareSvc[Cryptographic Share Link Resolver]
    end

    subgraph DataStore["Data & Persistence Layer (Supabase)"]
        SupaAuth[Supabase Auth Engine\nOTP & JWT Management]
        PG[(Supabase PostgreSQL\nwith Row Level Security)]
        Storage[(Supabase Private Storage\nmedical-reports bucket)]
    end

    A --> GW
    B --> GW
    C --> GW
    D --> GW

    GW --> API
    API --> AuthGuard
    AuthGuard --> RateLimiter
    RateLimiter --> AuditSvc
    RateLimiter --> StorageSvc
    RateLimiter --> ShareSvc

    API <--> SupaAuth
    API <--> PG
    StorageSvc -.->|Generate 5-min Signed URL| Storage
    Clients -.->|Direct Download via Signed URL| Storage
```

---

## 2. Frontend Architecture (Next.js & TypeScript)

The frontend uses Next.js with the **App Router**, structured into isolated route groups to guarantee separation of concerns between different user personas:

### 2.1 Route Groups & Layouts
- **`(patient)`**: Accessible only by authenticated patients.
  - `/patient/dashboard`: Summary of recent reports, active shares, and unique Patient ID card.
  - `/patient/reports`: Filterable medical report library (categorized by lab, radiology, prescription, etc.).
  - `/patient/upload`: Self-upload interface with client-side SHA-256 calculation and format validation.
  - `/patient/share`: QR code generation, active link management, access frequency tracking, and instant revocation.
  - `/patient/recovery`: Account recovery and phone update request flows.
- **`(hospital)`**: Accessible by authorized hospital staff.
  - `/hospital/login`: Organization-scoped clinician and staff login.
  - `/hospital/lookup`: Patient lookup via unique Patient ID with identity confirmation modal.
  - `/hospital/patient/[id]`: Medical report viewer with audit trail indicator.
  - `/hospital/upload`: Direct report upload with mandatory patient attribution and laboratory verification tag.
  - `/hospital/emergency`: Dedicated emergency break-glass triage interface.
- **`(admin)`**: Accessible by platform compliance officers.
  - `/admin/hospitals`: Hospital onboarding, verification, and deactivation.
  - `/admin/audit`: System-wide access log inspection and compliance alerting.
  - *Strict Rule*: Administrators cannot view patient medical files unless accompanied by a legally verified warrant and recorded audit entry.
- **`share/[token]`**: Public, zero-install viewer.
  - Accessible via expiring cryptographic token link or scanned QR code.
  - Displays only patient-consented documents; requires zero registration or app installation from the receiving doctor.

---

## 3. Backend Architecture (FastAPI & Python 3.12)

FastAPI acts as the secure intermediary and business logic enforcement engine:

```text
backend/app/
├── main.py              # Application lifecycle, CORS, exception handlers
├── core/
│   ├── config.py        # Environment variables validation via Pydantic BaseSettings
│   ├── security.py      # JWT decode, token hashing, role verification
│   └── database.py      # Supabase client initialization & session management
├── api/
│   └── v1/
│       ├── health.py    # Liveness and readiness probes
│       ├── patients.py  # Patient registration, de-duplication, and profile APIs
│       ├── reports.py   # Report metadata ingestion & signed upload/download URLs
│       ├── access.py    # Revocable QR grant issuance, access checks, revocation
│       ├── emergency.py # Break-glass emergency authorization & audit logging
│       └── hospital.py  # Hospital staff verification & patient record lookup
└── models/
    └── schemas.py       # Pydantic request/response models with strict type validation
```

### Key Responsibilities of the Backend:
1. **Token Authentication & Role Verification**: Verifies JWTs issued by Supabase Auth and validates user permissions against `users` and `hospital_staff` records.
2. **Access Control Enforcement**: Enforces that staff can only access records if authorized by hospital tenancy, active patient grant, or documented emergency override.
3. **Short-Lived Signed URL Issuance**: Coordinates with Supabase Storage to issue expiring URLs (e.g., 300 seconds), ensuring patient files are never exposed via permanent or public URLs.
4. **Audit Log Dispatch**: Synchronously writes audit entries to `audit_logs` and `emergency_access_logs` for every read, share, and upload action.

---

## 4. Database & Storage Boundaries (Supabase)

### 4.1 Database Layer (PostgreSQL)
- **Engine**: PostgreSQL 15+ managed by Supabase.
- **Security Boundaries**:
  - Direct database access from frontend client is restricted via strict Row-Level Security (RLS) policies.
  - Backend uses a scoped service role connection for administrative logging and emergency workflows, applying application-layer access controls.
- **Data Protection**:
  - Sensitive identifiers (like national IDs/Aadhaar) are never stored as plain text. Only cryptographic references and masked representations are retained.
  - Audit logs are append-only; update and delete operations are restricted via database triggers.

### 4.2 Storage Layer (Private S3-Compatible Buckets)
- **Bucket**: `medical-reports` (configured as private, non-public).
- **Naming Convention**: `reports/{patient_id}/{report_category}/{report_uuid}.{ext}`
- **Access Policy**:
  - Direct public access is disabled.
  - Read access requires an authenticated API call that generates a signed URL with a maximum 5-minute time-to-live (TTL).
  - Write access uses backend-generated pre-signed upload URLs with file size and MIME-type restrictions.

---

## 5. Security & Authorization Boundaries

```mermaid
graph LR
    subgraph Roles["User Roles"]
        P[Patient]
        S[Hospital Staff]
        A[Platform Admin]
        E[External Clinician]
    end

    subgraph AuthMethods["Authentication Mechanism"]
        OTP[Phone OTP]
        PW_MFA[Email/Password + MFA]
        ADMIN_AUTH[Admin Credential + Hardware Key]
        TOKEN[Cryptographic Share Token]
    end

    subgraph Permissions["Permission Boundary"]
        P_PERM[Own Profile & Uploads\nManage Grants & Recovery]
        S_PERM[Hospital Patient Lookup\nUpload Verified Reports\nEmergency Break-Glass]
        A_PERM[Manage Hospital Accounts\nAudit Log Monitoring\nNo Default PHI Access]
        E_PERM[Time-Bound Read-Only Access\nto Consented Reports Only]
    end

    P --> OTP --> P_PERM
    S --> PW_MFA --> S_PERM
    A --> ADMIN_AUTH --> A_PERM
    E --> TOKEN --> E_PERM
```

---

## 6. Core Data Flow Workflows

### 6.1 Report Upload Workflow (Hospital Staff or Patient)

```mermaid
sequenceDiagram
    autonumber
    actor U as Patient / Hospital Staff
    participant FE as Next.js App
    participant BE as FastAPI Backend
    participant DB as PostgreSQL DB
    participant ST as Supabase Private Storage

    U->>FE: Select file (PDF/Image) & enter metadata
    FE->>FE: Calculate client-side SHA-256 hash
    FE->>BE: POST /api/v1/reports/request-upload (meta, checksum, size)
    BE->>BE: Validate file type, size (<25MB), and user permissions
    BE->>DB: Insert report record (status: pending_upload)
    BE->>ST: Request Pre-signed Upload URL (TTL: 5 mins)
    ST-->>BE: Return Pre-signed Upload URL
    BE-->>FE: Return upload URL & report_id
    FE->>ST: PUT binary file directly to Pre-signed URL
    ST-->>FE: HTTP 200 OK
    FE->>BE: POST /api/v1/reports/{id}/confirm-upload
    BE->>ST: Verify file exists & verify checksum
    BE->>DB: Update report status to 'active' & write audit log
    BE-->>FE: Upload confirmed
    FE-->>U: Display report in library
```

### 6.2 Patient-Authorized Share via QR Code Workflow

```mermaid
sequenceDiagram
    autonumber
    actor P as Patient
    participant FE as Patient Portal
    participant BE as FastAPI Backend
    participant DB as PostgreSQL DB
    actor D as Non-Integrated Doctor
    participant DOC_FE as Browser (Zero-Install Viewer)
    participant ST as Supabase Private Storage

    P->>FE: Select reports to share & duration (e.g., 2 hours)
    FE->>BE: POST /api/v1/access/create-share
    BE->>BE: Generate cryptographic high-entropy grant token
    BE->>DB: Insert record_access_grants (hashed token, expiry, report_ids)
    BE-->>FE: Return share URL (e.g. /share/abc123xyz) & QR matrix data
    FE-->>P: Display QR Code on mobile screen
    P->>D: Doctor scans QR Code with standard mobile/tablet camera
    D->>DOC_FE: Browser opens /share/abc123xyz
    DOC_FE->>BE: GET /api/v1/access/view-share/{token}
    BE->>DB: Look up grant by token hash
    BE->>BE: Check expiry & revocation status
    BE->>DB: Increment access_count & write audit_log
    BE->>ST: Generate temporary signed URLs for granted reports
    BE-->>DOC_FE: Return report metadata & temporary download URLs
    DOC_FE-->>D: Renders reports securely in browser
```

### 6.3 Emergency Break-Glass Workflow

```mermaid
sequenceDiagram
    autonumber
    actor ER as ER Clinician
    participant FE as Hospital Portal
    participant BE as FastAPI Backend
    participant DB as PostgreSQL DB
    participant ST as Supabase Private Storage

    ER->>FE: Enter Patient ID & select "Emergency Break-Glass"
    FE-->>ER: Prompt with clinical emergency justification form
    ER->>FE: Select reason (e.g. Trauma/Unconscious) & submit clinical notes
    FE->>BE: POST /api/v1/emergency/break-glass (patient_id, reason, notes)
    BE->>BE: Verify Clinician is verified & hospital is active
    BE->>DB: Insert emergency_access_logs (clinician_id, hospital_id, timestamp, reason)
    BE->>DB: Insert urgent notification for patient profile
    BE->>DB: Query patient emergency medical records (blood group, allergies, recent history)
    BE->>ST: Generate temporary emergency signed URLs
    BE-->>FE: Return records with high-visibility "Emergency Mode" banner
    FE-->>ER: Display critical medical history immediately
    Note over DB,BE: Access record is flagged for hospital compliance review
```
