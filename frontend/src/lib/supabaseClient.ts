import { createClient, SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

/**
 * Checks whether Supabase public credentials have been supplied.
 */
export function isSupabaseConfigured(): boolean {
  return (
    Boolean(supabaseUrl) &&
    Boolean(supabaseAnonKey) &&
    !supabaseUrl.includes("your-project-id") &&
    !supabaseAnonKey.includes("your-supabase-public-anon-key")
  );
}

let supabaseInstance: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient | null {
  if (supabaseInstance) return supabaseInstance;

  if (isSupabaseConfigured()) {
    supabaseInstance = createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
      },
    });
    return supabaseInstance;
  }

  return null;
}

/**
 * Sends a One-Time Password (OTP) to the specified phone number.
 * Strict Rule: Never simulates successful OTP delivery in production.
 */
export async function sendPhoneOtp(phone: string) {
  const client = getSupabase();
  if (!client) {
    throw new Error(
      "Supabase is not configured. Please supply NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local."
    );
  }

  const { data, error } = await client.auth.signInWithOtp({
    phone: phone.trim(),
  });

  if (error) {
    throw new Error(error.message);
  }

  return data;
}

/**
 * Verifies the 6-digit OTP token entered by the user.
 */
export async function verifyPhoneOtp(phone: string, token: string) {
  const client = getSupabase();
  if (!client) {
    throw new Error(
      "Supabase is not configured. Please supply NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local."
    );
  }

  const { data, error } = await client.auth.verifyOtp({
    phone: phone.trim(),
    token: token.trim(),
    type: "sms",
  });

  if (error) {
    throw new Error(error.message);
  }

  return data;
}

/**
 * Signs the user out of the current session.
 */
export async function signOutPatient() {
  const client = getSupabase();
  if (client) {
    await client.auth.signOut();
  }
  if (typeof window !== "undefined") {
    localStorage.removeItem("med_report_token");
  }
}

/**
 * Retrieves the active session token for backend API authentication.
 */
export async function getAccessToken(): Promise<string | null> {
  const client = getSupabase();
  if (client) {
    const { data } = await client.auth.getSession();
    return data.session?.access_token || null;
  }
  if (typeof window !== "undefined") {
    return localStorage.getItem("med_report_token");
  }
  return null;
}
