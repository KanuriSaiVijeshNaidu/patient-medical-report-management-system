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

export interface SendEmailOtpOptions {
  shouldCreateUser?: boolean;
  emailRedirectTo?: string;
}

/**
 * Sends a One-Time Password (OTP) or magic link to the specified email address.
 *
 * @param email - Target email address
 * @param options - Optional configuration:
 *   - shouldCreateUser: Set to true for new account signup, or false for returning-user login
 *   - emailRedirectTo: Optional redirect URL if a magic link is clicked
 */
export async function sendEmailOtp(
  email: string,
  options?: SendEmailOtpOptions
) {
  const client = getSupabase();
  if (!client) {
    throw new Error(
      "Supabase is not configured. Please supply NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local."
    );
  }

  const cleanEmail = email.trim().toLowerCase();
  const shouldCreateUser = options?.shouldCreateUser ?? true;
  const redirectUrl =
    options?.emailRedirectTo ??
    (typeof window !== "undefined"
      ? `${window.location.origin}/patient/dashboard`
      : undefined);

  const { data, error } = await client.auth.signInWithOtp({
    email: cleanEmail,
    options: {
      shouldCreateUser,
      emailRedirectTo: redirectUrl,
    },
  });

  if (error) {
    throw new Error(error.message);
  }

  return data;
}

/**
 * Verifies the 6-digit OTP token sent to the user's email address.
 */
export async function verifyEmailOtp(email: string, token: string) {
  const client = getSupabase();
  if (!client) {
    throw new Error(
      "Supabase is not configured. Please supply NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local."
    );
  }

  const cleanEmail = email.trim().toLowerCase();
  const { data, error } = await client.auth.verifyOtp({
    email: cleanEmail,
    token: token.trim(),
    type: "email",
  });

  if (error) {
    throw new Error(error.message);
  }

  if (data?.session?.access_token && typeof window !== "undefined") {
    localStorage.setItem("med_report_token", data.session.access_token);
  }

  return data;
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

  const cleanPhone = phone.replace(/\s+/g, "");
  const { data, error } = await client.auth.signInWithOtp({
    phone: cleanPhone,
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

  const cleanPhone = phone.replace(/\s+/g, "");
  const { data, error } = await client.auth.verifyOtp({
    phone: cleanPhone,
    token: token.trim(),
    type: "sms",
  });

  if (error) {
    throw new Error(error.message);
  }

  if (data?.session?.access_token && typeof window !== "undefined") {
    localStorage.setItem("med_report_token", data.session.access_token);
  }

  return data;
}

/**
 * Removes local session tokens and notifies listening components.
 */
export function clearAuthToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("med_report_token");
    sessionStorage.clear();
    window.dispatchEvent(new Event("auth-state-change"));
  }
}

/**
 * Signs the user out of the current session.
 * Guarantees local token destruction even if Supabase network call fails.
 */
export async function signOutPatient() {
  try {
    const client = getSupabase();
    if (client) {
      await client.auth.signOut().catch(() => {});
    }
  } catch {
    // Ignore network or configuration errors during remote sign-out
  } finally {
    clearAuthToken();
  }
}

/**
 * Retrieves the active session token for backend API authentication.
 * Checks local storage for username/password JWT first, falling back to Supabase session.
 */
export async function getAccessToken(): Promise<string | null> {
  if (typeof window !== "undefined") {
    const localToken = localStorage.getItem("med_report_token");
    if (localToken && localToken.trim()) {
      return localToken.trim();
    }
  }

  const client = getSupabase();
  if (client) {
    try {
      const { data } = await client.auth.getSession();
      if (data?.session?.access_token) {
        if (typeof window !== "undefined") {
          localStorage.setItem("med_report_token", data.session.access_token);
        }
        return data.session.access_token;
      }
    } catch {
      // Fall through to null
    }
  }

  return null;
}
