# Requirements Specification Document
## Patient Medical Report Management System

**Version:** 1.0.0-draft  
**Last Updated:** October 2026  
**Target Environment:** Web (Responsive Desktop & Mobile)  

---

## 1. Executive Summary

The **Patient Medical Report Management System** is a dedicated digital health platform designed to give patients complete ownership and control over their medical history while enabling integrated hospitals and external healthcare providers to securely view, upload, and verify diagnostic reports and medical documentation.

---

## 2. Scope Boundaries

### 2.1 In Scope (Phase 1)
- **Patient Registration & Identity Management**: Phone OTP verification, permanent unique Patient ID assignment, duplicate profile prevention, and phone number recovery.
- **Medical Report Storage & Categorization**: Secure storage of blood tests, imaging (X-rays, CT scans, MRI), prescriptions, discharge summaries, and clinical notes.
- **Integrated Hospital Operations**: Authorized staff authentication, patient lookup by Patient ID, verified report uploading, and hospital-scoped access control.
- **Non-Integrated Hospital Sharing**: Time-bound, revocable QR code and link sharing for browser-based, zero-installation record viewing.
- **Emergency "Break-Glass" Access**: Non-blocking emergency access workflow for verified clinicians with mandatory clinical justification and immutable audit tracking.
- **Security & Privacy Infrastructure**: PostgreSQL Row-Level Security (RLS), private object storage with signed URLs, cryptographic checksums, and comprehensive audit logs.

### 2.2 Out of Scope (Explicitly Deferred)
The following features are **strictly excluded** from this phase:
- Outpatient/inpatient appointment scheduling.
- Hospital OPD queue management and live waiting-time estimation.
- WhatsApp automated messaging bots for appointment or queue reminders.
- Prescription and medicine adherence reminders.
- Billing, insurance claim processing, or payment gateway integration.

---

## 3. Core Functional Requirements

### 3.1 Patient Registration & Identity

| ID | Requirement | Description |
|---|---|---|
| **REQ-ID-01** | **OTP Verification** | Registration and authentication must verify the patient's mobile number via a secure One-Time Password (OTP) provider. |
| **REQ-ID-02** | **Unique Patient ID** | System must generate a permanent, human-readable, collision-resistant Patient ID (e.g., `MED-YYYY-XXXXXX`). This ID never changes across phone number updates. |
| **REQ-ID-03** | **De-duplication Protection** | A verification workflow based on normalized full name, date of birth, gender, and cryptographic phone hashes must identify potential duplicates before creating new profiles. |
| **REQ-ID-04** | **Aadhaar Policy Compliance** | Aadhaar numbers must **never** be used as database primary keys, stored in raw plaintext, or exposed in API payloads or QR codes. Aadhaar verification must only be conducted through UIDAI-licensed AUA/KUA entities or authorized Ayushman Bharat Digital Mission (ABDM) ABHA workflows. Only verified reference tokens and masked digits (e.g., `XXXX-XXXX-1234`) are retained. |
| **REQ-ID-05** | **Account Recovery** | If a patient changes or loses their registered phone number, a secure multi-step recovery flow (security questions, email fallback, or in-person hospital desk verification) must update the credential without spawning a duplicate medical history. |

### 3.2 Medical Report Storage & Management

| ID | Requirement | Description |
|---|---|---|
| **REQ-REP-01** | **Document Categories** | System must support categorizing documents into: *Blood Tests & Pathology, Radiology (X-Ray, CT, MRI, Ultrasound), Prescriptions, Discharge Summaries, Operative Notes, and Other Consultations*. |
| **REQ-REP-02** | **Supported Formats & Size** | Support PDF, JPEG, PNG, and DICOM web preview exports. File upload size limit enforced at gateway (e.g., 25MB per document). |
| **REQ-REP-03** | **Required Metadata** | Every stored report must capture: `report_id`, `patient_id`, `title`, `category`, `report_date`, `upload_date`, `source_type` (`patient` or `hospital`), `source_hospital_id` (if applicable), `source_staff_id` (if applicable), `verification_status` (`unverified`, `hospital_verified`, `system_verified`), `file_storage_path`, `file_checksum_sha256`, and `file_size_bytes`. |
| **REQ-REP-04** | **Private File Storage** | Raw files must reside exclusively in private object storage buckets. Direct public URL access is prohibited. File retrieval occurs strictly via short-lived signed URLs (default lifespan: 5 minutes) issued only after authorization. |
| **REQ-REP-05** | **File Integrity** | During upload, a SHA-256 cryptographic hash is computed and stored to detect tampering or corruption. |

### 3.3 Integrated Hospital Operations

| ID | Requirement | Description |
|---|---|---|
| **REQ-HOS-01** | **Staff Authentication** | Hospital clinicians and administrative staff authenticate via dedicated credentials linked to a verified hospital organization profile. |
| **REQ-HOS-02** | **Patient Record Lookup** | Staff can search for patient profiles using the unique Patient ID. Basic identity details (masked name, age/DOB, gender) are presented for confirmation before clinical history is surfaced. |
| **REQ-HOS-03** | **Authorized Report Uploads** | Staff can upload diagnostic reports directly to the verified patient profile. Uploads are automatically attributed to the originating hospital and authenticated staff member, and marked as `hospital_verified`. |
| **REQ-HOS-04** | **Cross-Hospital Isolation** | By default, an integrated hospital can only view records uploaded by its own facility unless explicit patient consent/grant or emergency access is active. |

### 3.4 Non-Integrated Hospitals & Revocable Sharing

| ID | Requirement | Description |
|---|---|---|
| **REQ-SHR-01** | **Patient-Controlled Sharing** | Patients can select specific reports or entire health summaries to share with doctors or non-integrated healthcare facilities. |
| **REQ-SHR-02** | **Expiring QR Code & Link** | The system generates a time-limited (e.g., 1 hour to 7 days) and revocable access link / QR code. |
| **REQ-SHR-03** | **Zero Sensitive Data in QR** | QR codes and share URLs contain only high-entropy cryptographic grant tokens. Under no circumstances may raw medical files, Aadhaar numbers, or user passwords be embedded in the QR payload. |
| **REQ-SHR-04** | **Zero-Install Web Viewer** | External healthcare workers can open the link in any modern web browser to view the authorized documents without creating an account or installing proprietary software. |
| **REQ-SHR-05** | **Revocation & Access Logs** | Patients can immediately revoke an active link at any time from their dashboard. Each view via the link increments an access counter and is logged in the audit trail. |

### 3.5 Emergency "Break-Glass" Access

| ID | Requirement | Description |
|---|---|---|
| **REQ-EMG-01** | **Non-Blocking Access** | In life-threatening emergencies where a patient is unconscious, incapacitated, or unable to receive/recite an OTP, authorized hospital medical staff can invoke emergency access. |
| **REQ-EMG-02** | **Clinical Justification** | Staff must select a standard triage emergency reason and provide mandatory clinical justification notes prior to record exposure. |
| **REQ-EMG-03** | **Practitioner Verification** | Emergency access is restricted to verified, active clinical staff with verified medical registration credentials. |
| **REQ-EMG-04** | **Immutable Audit & Review** | All break-glass access events generate an immediate immutable log detailing practitioner ID, hospital ID, patient ID, timestamp, IP, and reason. The event is flagged for hospital clinical compliance audit review. Patient dashboard shows emergency access notifications. |

---

## 4. Privacy, Security & Regulatory Guidelines

### 4.1 Security Principles
- **Authentication**: JWT-based session tokens with strict expiration and refresh rotation.
- **Authorization**: Mandatory server-side authorization checks on all REST endpoints; PostgreSQL Row-Level Security (RLS) policies as defense-in-depth.
- **Data Encryption**:
  - In transit: TLS 1.3 enforced for all web and API traffic.
  - At rest: AES-256 encryption on database tables and object storage.
- **Rate Limiting**: Anti-brute force and anti-scraping rate limits on phone OTP requests, patient lookups, and share link resolutions.

### 4.2 Regulatory Considerations (Indian Healthcare Context)
- **Digital Personal Data Protection (DPDP) Act, 2023**: Clear purpose limitation, explicit consent mechanisms for data sharing, right to view access history, and right to withdraw consent (link revocation).
- **Aadhaar Act, 2016 & UIDAI Regulations**: Aadhaar numbers are never stored in raw form; biometric data is never touched or stored; no denial of emergency care based on Aadhaar status.
- **DISHA (Digital Information Security in Healthcare Act) Principles**: Maintaining an unalterable audit log for all health data views, transfers, and alterations.
- **Note**: Adding security features does not constitute full statutory compliance. Formal legal and clinical governance reviews are required prior to live medical deployment.
