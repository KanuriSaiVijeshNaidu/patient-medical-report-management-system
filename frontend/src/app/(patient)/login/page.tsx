"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ShieldCheck,
  Phone,
  KeyRound,
  ArrowRight,
  AlertCircle,
  Loader2,
  RefreshCw,
  Info,
} from "lucide-react";
import {
  sendPhoneOtp,
  verifyPhoneOtp,
  isSupabaseConfigured,
} from "@/lib/supabaseClient";
import { getMyProfile } from "@/lib/api";

export default function PatientLoginPage() {
  const router = useRouter();

  const [phone, setPhone] = useState("+91");
  const [otpToken, setOtpToken] = useState("");
  const [step, setStep] = useState<"phone" | "otp">("phone");
  const [countdown, setCountdown] = useState(0);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);
  const [configured, setConfigured] = useState(true);

  useEffect(() => {
    setConfigured(isSupabaseConfigured());
  }, []);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (countdown > 0) {
      timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    }
    return () => clearTimeout(timer);
  }, [countdown]);

  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setInfoMsg(null);

    const cleanPhone = phone.trim();
    if (cleanPhone.length < 10) {
      setErrorMsg("Please enter a valid mobile number with country code.");
      return;
    }

    if (!configured) {
      setErrorMsg(
        "Supabase Auth is not configured. Please add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY to frontend/.env.local to enable real OTP delivery."
      );
      return;
    }

    setLoading(true);
    try {
      await sendPhoneOtp(cleanPhone);
      setStep("otp");
      setCountdown(60);
      setInfoMsg(`OTP has been dispatched via SMS to ${cleanPhone}`);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to send OTP. Please verify phone number.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (otpToken.length < 6) {
      setErrorMsg("Please enter the complete 6-digit OTP code.");
      return;
    }

    setLoading(true);
    try {
      await verifyPhoneOtp(phone, otpToken);
      // Check if profile already exists in backend
      try {
        await getMyProfile();
        // Profile exists -> redirect to dashboard
        router.push("/patient/dashboard");
      } catch (profileErr: any) {
        // If 404 (first time user), redirect to registration
        if (profileErr.message?.includes("not found") || profileErr.message?.includes("404")) {
          router.push("/patient/register");
        } else {
          // If other error (e.g. backend offline), go to dashboard which handles error state
          router.push("/patient/dashboard");
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Invalid or expired OTP. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-12 px-4 space-y-8">
      {/* Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 mb-2">
          <ShieldCheck className="w-6 h-6" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Patient Authentication
        </h1>
        <p className="text-sm text-slate-600">
          Sign in or register securely using your mobile number and One-Time Password (OTP).
        </p>
      </div>

      {/* Unconfigured Alert Banner */}
      {!configured && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-800 space-y-1.5">
          <div className="font-semibold flex items-center gap-1.5 text-amber-900">
            <Info className="w-4 h-4 text-amber-600" /> External Service Setup Required
          </div>
          <p>
            Supabase Auth credentials have not yet been provided. To test live SMS OTP delivery, copy <code className="bg-amber-100 px-1 py-0.5 rounded font-mono">.env.example</code> to <code className="bg-amber-100 px-1 py-0.5 rounded font-mono">.env.local</code> and provide your Supabase project keys.
          </p>
        </div>
      )}

      {/* Main Form Card */}
      <div className="bg-white p-6 sm:p-8 rounded-2xl border border-slate-200 shadow-sm space-y-6">
        {errorMsg && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl p-3 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{errorMsg}</span>
          </div>
        )}

        {infoMsg && (
          <div className="bg-blue-50 border border-blue-200 text-blue-700 text-xs rounded-xl p-3 flex items-start gap-2">
            <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{infoMsg}</span>
          </div>
        )}

        {step === "phone" ? (
          <form onSubmit={handleSendOtp} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                Mobile Number
              </label>
              <div className="relative">
                <Phone className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+91 98765 43210"
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-slate-900 text-sm"
                  required
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Include country code (e.g. +91 for India).
              </p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg flex items-center justify-center gap-2 transition disabled:opacity-60 shadow-sm"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Sending OTP...
                </>
              ) : (
                <>
                  Send Verification OTP <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerifyOtp} className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Enter 6-Digit OTP
                </label>
                <button
                  type="button"
                  onClick={() => setStep("phone")}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Change number
                </button>
              </div>
              <div className="relative">
                <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="text"
                  maxLength={6}
                  value={otpToken}
                  onChange={(e) => setOtpToken(e.target.value.replace(/\D/g, ""))}
                  placeholder="123456"
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-center tracking-widest text-lg font-bold text-slate-900"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg flex items-center justify-center gap-2 transition disabled:opacity-60 shadow-sm"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Verifying...
                </>
              ) : (
                "Verify & Continue"
              )}
            </button>

            <div className="pt-2 text-center text-xs text-slate-500">
              {countdown > 0 ? (
                <span>Resend OTP in {countdown} seconds</span>
              ) : (
                <button
                  type="button"
                  onClick={handleSendOtp}
                  className="text-blue-600 hover:underline inline-flex items-center gap-1"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Resend OTP
                </button>
              )}
            </div>
          </form>
        )}

        <div className="border-t border-slate-100 pt-4 text-center">
          <p className="text-xs text-slate-600">
            Lost access to your registered number?{" "}
            <Link
              href="/patient/recovery"
              className="text-blue-600 font-medium hover:underline"
            >
              Recover existing account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
