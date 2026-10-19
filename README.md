# Patient Medical Report Management System

A secure, patient-centric healthcare platform for managing, organizing, and sharing medical records between patients, integrated hospitals, and non-integrated medical providers.

---

## 1. Project Overview & Current Status

- **Status**: Phase 1 — Project Initialization, Architecture & Schema Specification (Not yet in active production).
- **Core Focus**: Exclusively Patient Medical Report Management.
- **Out of Scope for Current Phase**:
  - Appointment scheduling
  - Hospital queue management & waiting-time estimations
  - WhatsApp notification bots for queues/appointments
  - Medicine/prescription adherence reminders

---

## 2. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Frontend** | Next.js 14+ (App Router), TypeScript, Tailwind CSS, Lucide React | Server/client component split, responsive UI, strict type safety |
| **Backend** | Python 3.12+, FastAPI, Pydantic v2 | High-performance asynchronous REST APIs, declarative schema validation |
| **Database & Auth** | Supabase PostgreSQL, Supabase Auth | Managed PostgreSQL with native Row-Level Security (RLS) & OTP authentication |
| **Document Storage**| Supabase Storage (Private Buckets) | S3-compatible private object store with time-limited signed URL access |
| **Environment** | Windows 11 / Linux compatible, Node.js v24+, Python venv | Cross-platform development standards |

---

## 3. Project Structure

```text
report_system/
├── README.md                          # Project documentation and quickstart
├── .gitignore                         # Git exclusion rules
├── .env.example                       # Root environment variables reference
├── docs/                              # Formal architectural and design specifications
│   ├── requirements.md                # Functional, security & compliance requirements
│   ├── architecture.md                # System topology, data flow & security boundaries
│   └── database-schema.md             # Entity relationships, tables, indexes & RLS policies
├── backend/                           # FastAPI application & database migrations
│   ├── requirements.txt               # Python package dependencies
│   ├── .env.example                   # Backend environment variables template
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI entrypoint with health check
│   │   ├── core/                      # App configuration, logging & security utils
│   │   │   ├── __init__.py
│   │   │   └── config.py              # Pydantic BaseSettings for env loading
│   │   ├── api/                       # API route modules (v1)
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── health.py          # Liveness and readiness endpoints
│   │   │       ├── patients.py        # Patient profile & lookup endpoints (stub)
│   │   │       ├── reports.py         # Report metadata & upload URL endpoints (stub)
│   │   │       ├── access.py          # QR & revocable share endpoints (stub)
│   │   │       ├── emergency.py       # Break-glass emergency access endpoints (stub)
│   │   │       └── hospital.py        # Hospital staff record access (stub)
│   │   └── models/                    # Pydantic data schemas
│   │       ├── __init__.py
│   │       └── schemas.py             # Request/response validation schemas
│   └── supabase/
│       └── migrations/
│           └── 20261019000001_initial_schema.sql # Complete PostgreSQL DDL & RLS policies
└── frontend/                          # Next.js TypeScript application
    ├── package.json                   # Frontend dependencies and scripts
    ├── tsconfig.json                  # TypeScript compiler configuration
    ├── next.config.mjs                # Next.js configuration
    ├── tailwind.config.ts             # Tailwind CSS styling configuration
    ├── postcss.config.js              # PostCSS plugins configuration
    ├── .env.example                   # Frontend environment variables template
    └── src/
        ├── app/                       # Next.js App Router
        │   ├── layout.tsx             # Root layout with font and metadata
        │   ├── page.tsx               # Landing page & portal entry selection
        │   ├── (patient)/             # Patient portal routes
        │   ├── (hospital)/            # Hospital staff portal routes
        │   ├── (admin)/               # Administrative management routes
        │   └── share/
        │       └── [token]/           # Public zero-install recipient report viewer
        ├── components/                # Reusable UI component library
        └── lib/                       # Utility functions & API clients
```

---

## 4. Prerequisites

Before running the application locally, ensure you have:
1. **Node.js**: v20+ (v24.19.0 recommended) and **npm**: v10+
2. **Python**: v3.11+ (v3.12.10 recommended)
3. **Supabase Account / CLI**: A Supabase project with PostgreSQL and Storage enabled.

---

## 5. Getting Started (Development Setup)

### A. Backend Setup (FastAPI)

1. Open PowerShell and navigate to the backend directory:
   ```powershell
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Copy environment configuration and supply your keys:
   ```powershell
   Copy-Item .env.example .env
   ```
5. Run the development server:
   ```powershell
   uvicorn app.main:app --reload --port 8000
   ```
   Backend health check will be available at: `http://localhost:8000/api/v1/health`

### B. Frontend Setup (Next.js)

1. Open a new terminal and navigate to the frontend directory:
   ```powershell
   cd frontend
   ```
2. Install dependencies:
   ```powershell
   npm install
   ```
3. Copy environment configuration:
   ```powershell
   Copy-Item .env.example .env.local
   ```
4. Run the frontend development server:
   ```powershell
   npm run dev
   ```
   Frontend will be accessible at: `http://localhost:3000`

### C. Database Initialization

Execute the SQL script located at `backend/supabase/migrations/20261019000001_initial_schema.sql` via the Supabase SQL Editor or Supabase CLI (`supabase db push`).

---

## 6. External Services Requiring Configuration

The following services must be configured before full system integration:
1. **Supabase Project**: Requires Supabase Project URL, Public Anon Key, and Service Role Key (for backend server-side operations only).
2. **Supabase Storage Bucket**: A private bucket named `medical-reports` must be created with public access disabled.
3. **SMS / OTP Gateway**: Required for phone verification (e.g., Twilio, MSG91, or Supabase Phone Auth).
4. **Identity Verification Provider**: Authorized identity/Aadhaar verification partner (e.g., ABDM sandbox or UIDAI-approved AUA/KUA partner). *Note: Direct handling of Aadhaar is strictly regulated under the Aadhaar Act 2016 and DPDP Act 2023.*

---

## 7. Security & Compliance Principles

- **Zero Public File Buckets**: All medical assets are private; pre-signed, time-limited URLs (e.g., 5-minute lifespan) are generated on demand following authentication and authorization checks.
- **Strict Row-Level Security**: PostgreSQL RLS ensures data isolation across patients and hospitals.
- **Break-Glass Emergency Access**: Allows medical practitioners to access records during life-critical emergencies with mandatory reason categorization, practitioner verification, and immutable auditing for subsequent compliance reviews.
- **Zero-Install Authorized Sharing**: Expiring, revocable cryptographic tokens allow non-integrated healthcare providers to inspect shared reports without installing apps or storing permanent credentials.
