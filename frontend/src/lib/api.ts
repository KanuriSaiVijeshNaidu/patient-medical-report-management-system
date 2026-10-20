import { getAccessToken } from "./supabaseClient";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface PatientProfile {
  id: string;
  patient_id: string;
  full_name: string;
  date_of_birth: string;
  gender: "male" | "female" | "other" | "prefer_not_to_say";
  blood_group?: string;
  emergency_contact_phone?: string;
  verification_status: string;
  phone_masked?: string;
  created_at: string;
  updated_at?: string;
  masked_aadhaar_ref?: string;
}

export interface PatientRegisterInput {
  full_name: string;
  username: string;
  password: string;
  gender: "male" | "female" | "other" | "prefer_not_to_say";
  phone: string;
  blood_group: string;
}

export interface PatientRegisterResult {
  patient_id: string;
  full_name: string;
  username: string;
  access_token: string;
  token_type: string;
  message: string;
}

export interface PatientLoginInput {
  username: string;
  password: string;
}

export interface PatientLoginResult {
  access_token: string;
  token_type: string;
  patient_id: string;
  username: string;
  full_name: string;
}

export interface PatientProfileInput {
  full_name: string;
  date_of_birth: string;
  gender: "male" | "female" | "other" | "prefer_not_to_say";
  blood_group?: string;
  emergency_contact_phone?: string;
}

export interface PatientProfileUpdateInput {
  blood_group?: string;
  emergency_contact_phone?: string;
}

export interface RecoveryInitiateInput {
  target_patient_id: string;
  challenge_date_of_birth: string;
  challenge_emergency_contact_phone?: string;
}

export interface MedicalReport {
  id: string;
  report_id: string;
  patient_id: string;
  hospital_id?: string | null;
  upload_source: "patient" | "hospital";
  title: string;
  category: "blood_test" | "xray" | "ct_scan" | "mri" | "prescription" | "discharge_summary" | "other";
  report_date: string;
  file_size_bytes: number;
  mime_type: string;
  verification_status: "unverified" | "hospital_verified";
  created_at: string;
  metadata?: Record<string, any>;
}

export interface ReportDownloadUrlResponse {
  report_id: string;
  download_url: string;
  expires_in_seconds: number;
}

export interface ReportDeleteResponse {
  success: boolean;
  message: string;
  report_id: string;
}

export interface UploadReportInput {
  file: File;
  title: string;
  category: string;
  report_date: string;
  description?: string;
}

/**
 * Base authenticated fetch wrapper. Attaches Supabase Bearer token.
 */
async function authFetch(endpoint: string, options: RequestInit = {}) {
  const token = await getAccessToken();

  if (!token) {
    throw new Error(
      "Authentication required. Please sign in to continue."
    );
  }

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  // Only set application/json if body is not FormData
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  headers["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    });
  } catch (err: any) {
    const isNetworkError =
      err?.name === "TypeError" ||
      err?.message?.includes("fetch") ||
      err?.message?.includes("network");
    if (isNetworkError) {
      throw new Error(
        `Unable to reach the backend server at ${API_BASE_URL}. Please ensure the backend is running.`
      );
    }
    throw err;
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    if (response.status === 401) {
      // Stale or invalid session: clear client token
      if (typeof window !== "undefined") {
        localStorage.removeItem("med_report_token");
        sessionStorage.clear();
        window.dispatchEvent(new Event("auth-state-change"));
      }
      throw new Error("Authentication required. Please sign in to continue.");
    }
    const errorMsg =
      data?.detail || `API request failed with status ${response.status}`;
    throw new Error(errorMsg);
  }

  return data;
}

/**
 * Registers a new patient with username and password.
 */
export async function registerPatient(
  payload: PatientRegisterInput
): Promise<PatientRegisterResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/patients/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err: any) {
    const isNetworkError =
      err?.name === "TypeError" ||
      err?.message?.includes("fetch") ||
      err?.message?.includes("network");
    if (isNetworkError) {
      throw new Error(
        `Unable to reach the backend server at ${API_BASE_URL}. Please ensure the backend is running.`
      );
    }
    throw err;
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg = data?.detail || "Registration failed. Please check your details.";
    throw new Error(errorMsg);
  }

  if (data?.access_token && typeof window !== "undefined") {
    localStorage.setItem("med_report_token", data.access_token);
    window.dispatchEvent(new Event("auth-state-change"));
  }

  return data;
}

/**
 * Authenticates an existing patient with username and password.
 */
export async function loginPatient(
  payload: PatientLoginInput
): Promise<PatientLoginResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/patients/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err: any) {
    const isNetworkError =
      err?.name === "TypeError" ||
      err?.message?.includes("fetch") ||
      err?.message?.includes("network") ||
      err?.message?.includes("NetworkError");
    if (isNetworkError) {
      throw new Error(
        `Unable to reach the backend server at ${API_BASE_URL}. Please ensure the backend is running.`
      );
    }
    throw err;
  }

  let data: any = null;
  try {
    data = await response.json();
  } catch {
    // Non-JSON response
  }

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error(data?.detail || "Invalid username or password.");
    }
    if (response.status === 404) {
      throw new Error(data?.detail || "Patient account not found. Please register first.");
    }
    if (response.status === 429) {
      throw new Error(data?.detail || "Too many sign-in attempts. Please wait a moment and try again.");
    }
    if (response.status === 422) {
      throw new Error(
        Array.isArray(data?.detail)
          ? data.detail[0]?.msg || "Please provide both username and password."
          : data?.detail || "Please provide both username and password."
      );
    }
    throw new Error(data?.detail || `Sign in failed (HTTP ${response.status}).`);
  }

  if (data?.access_token && typeof window !== "undefined") {
    localStorage.setItem("med_report_token", data.access_token);
    window.dispatchEvent(new Event("auth-state-change"));
  }

  return data;
}

/**
 * Fetches current authenticated patient profile.
 */
export async function getMyProfile(): Promise<PatientProfile> {
  return authFetch("/patients/me", { method: "GET" });
}

/**
 * Creates a new patient profile after OTP verification.
 */
export async function createProfile(
  payload: PatientProfileInput
): Promise<PatientProfile> {
  return authFetch("/patients/profile", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Updates patient clinical/contact information.
 */
export async function updateProfile(
  payload: PatientProfileUpdateInput
): Promise<PatientProfile> {
  return authFetch("/patients/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/**
 * Initiates an account recovery challenge.
 */
export async function initiateRecovery(payload: RecoveryInitiateInput) {
  return authFetch("/patients/recovery/initiate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Confirms and completes account recovery.
 */
export async function verifyRecovery(recoveryRequestId: string) {
  return authFetch("/patients/recovery/verify", {
    method: "POST",
    body: JSON.stringify({ recovery_request_id: recoveryRequestId }),
  });
}

/**
 * Lists categorized medical reports belonging to the authenticated patient.
 */
export async function getMyReports(category?: string): Promise<MedicalReport[]> {
  const query = category && category !== "all" ? `?category=${encodeURIComponent(category)}` : "";
  return authFetch(`/reports${query}`, { method: "GET" });
}

/**
 * Fetches single medical report details.
 */
export async function getReportById(reportId: string): Promise<MedicalReport> {
  return authFetch(`/reports/${encodeURIComponent(reportId)}`, { method: "GET" });
}

/**
 * Securely uploads a patient medical report PDF document.
 */
export async function uploadMedicalReport(payload: UploadReportInput): Promise<MedicalReport> {
  const formData = new FormData();
  formData.append("file", payload.file);
  formData.append("title", payload.title);
  formData.append("category", payload.category);
  formData.append("report_date", payload.report_date);
  if (payload.description) {
    formData.append("description", payload.description);
  }

  return authFetch("/reports/upload", {
    method: "POST",
    body: formData,
  });
}

/**
 * Obtains a short-lived pre-signed download URL for a medical report PDF.
 */
export async function getReportDownloadUrl(reportId: string): Promise<ReportDownloadUrlResponse> {
  return authFetch(`/reports/${encodeURIComponent(reportId)}/download-url`, {
    method: "POST",
  });
}

/**
 * Deletes a medical report owned by the authenticated patient.
 */
export async function deleteMedicalReport(reportId: string): Promise<ReportDeleteResponse> {
  return authFetch(`/reports/${encodeURIComponent(reportId)}`, {
    method: "DELETE",
  });
}

export interface ShareGrantResponse {
  grant_id: string;
  report_id: string;
  report_ids?: string[];
  reports_count?: number;
  share_url: string;
  raw_token: string;
  expires_at: string;
  expires_in_seconds: number;
}

export interface SharedReportItem {
  report_id: string;
  title: string;
  category: string;
  report_date: string;
  file_size_bytes: number;
  mime_type: string;
  verification_status: string;
  download_url: string;
  download_url_expires_in_seconds: number;
}

export interface SharedReportViewResponse {
  grant_id: string;
  report_id: string;
  title: string;
  category: string;
  report_date: string;
  file_size_bytes: number;
  mime_type: string;
  verification_status: string;
  download_url: string;
  download_url_expires_in_seconds: number;
  share_expires_at: string;
  reports?: SharedReportItem[];
}

export interface RevokeShareResponse {
  success: boolean;
  message: string;
  grant_id: string;
  revoked_at: string;
}

/**
 * Creates an expiring QR share grant for one or more specific medical reports.
 */
export async function createReportShare(
  reportIds: string | string[],
  expiresInSeconds: number = 900
): Promise<ShareGrantResponse> {
  const payload = Array.isArray(reportIds)
    ? { report_ids: reportIds, expires_in_seconds: expiresInSeconds }
    : { report_id: reportIds, expires_in_seconds: expiresInSeconds };

  return authFetch("/access/create-share", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Immediately revokes an active report share grant.
 */
export async function revokeReportShare(grantId: string): Promise<RevokeShareResponse> {
  return authFetch(`/access/revoke/${encodeURIComponent(grantId)}`, {
    method: "DELETE",
  });
}

/**
 * Public recipient function: validates share token and retrieves temporary view data.
 */
export async function viewSharedReport(token: string): Promise<SharedReportViewResponse> {
  const response = await fetch(`${API_BASE_URL}/access/view/${encodeURIComponent(token)}`);
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg = data?.detail || `Unable to access report (${response.status})`;
    throw new Error(errorMsg);
  }

  return data;
}

// -----------------------------------------------------------------------------
// Hospital Staff & Doctor Patient Lookup API
// -----------------------------------------------------------------------------
export interface HospitalStaffLoginInput {
  email: string;
  password: string;
  hospital_registration_number?: string;
}

export interface HospitalStaffLoginResult {
  access_token: string;
  token_type: string;
  staff_id: string;
  staff_name: string;
  staff_role: string;
  employee_id: string;
  hospital_id: string;
  hospital_name: string;
  hospital_registration_number: string;
}

export interface DoctorPatientInfo {
  patient_id: string;
  full_name: string;
  gender: string;
  blood_group?: string;
  date_of_birth?: string;
}

export interface DoctorPatientLookupResponse {
  authorized: boolean;
  patient: DoctorPatientInfo;
  hospital_name: string;
  hospital_id: string;
  reports: SharedReportItem[];
}

export async function loginHospitalStaff(
  input: HospitalStaffLoginInput
): Promise<HospitalStaffLoginResult> {
  const response = await fetch(`${API_BASE_URL}/hospital/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg = data?.detail || `Authentication failed (${response.status})`;
    throw new Error(errorMsg);
  }

  if (typeof window !== "undefined") {
    localStorage.setItem("med_hospital_token", data.access_token);
    localStorage.setItem("med_hospital_staff", JSON.stringify(data));
    window.dispatchEvent(new Event("hospital-auth-change"));
  }

  return data;
}

export function getHospitalStaffToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("med_hospital_token");
  }
  return null;
}

export function getHospitalStaffInfo(): HospitalStaffLoginResult | null {
  if (typeof window !== "undefined") {
    const raw = localStorage.getItem("med_hospital_staff");
    if (raw) {
      try {
        return JSON.parse(raw);
      } catch {
        return null;
      }
    }
  }
  return null;
}

export function clearHospitalStaffAuth(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("med_hospital_token");
    localStorage.removeItem("med_hospital_staff");
    window.dispatchEvent(new Event("hospital-auth-change"));
  }
}

export async function doctorLookupPatient(
  patientId: string
): Promise<DoctorPatientLookupResponse> {
  const token = getHospitalStaffToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(
    `${API_BASE_URL}/hospital/patient/${encodeURIComponent(patientId.trim().toUpperCase())}`,
    {
      method: "GET",
      headers,
    }
  );

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const err: any = new Error(data?.detail || `Lookup failed (${response.status})`);
    err.status = response.status;
    err.detail = data?.detail;
    throw err;
  }

  return data;
}

export async function getHospitalReportDownloadUrl(
  reportId: string
): Promise<{ report_id: string; title: string; download_url: string; expires_in_seconds: number }> {
  const token = getHospitalStaffToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(
    `${API_BASE_URL}/hospital/reports/${encodeURIComponent(reportId)}/download-url`,
    {
      method: "GET",
      headers,
    }
  );

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const err: any = new Error(data?.detail || `Download failed (${response.status})`);
    err.status = response.status;
    throw err;
  }

  return data;
}
