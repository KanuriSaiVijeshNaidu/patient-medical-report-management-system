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

/**
 * Base authenticated fetch wrapper. Attaches Supabase Bearer token.
 */
async function authFetch(endpoint: string, options: RequestInit = {}) {
  const token = await getAccessToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.detail || `API request failed with status ${response.status}`;
    throw new Error(errorMsg);
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
