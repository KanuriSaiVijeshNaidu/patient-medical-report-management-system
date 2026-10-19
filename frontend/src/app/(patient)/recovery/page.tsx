"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ShieldAlert,
  ArrowRight,
  AlertCircle,
  Loader2,
  CheckCircle2,
  KeyRound,
  ArrowLeft,
} from "lucide-react";
import { initiateRecovery, verifyRecovery } from "@/lib/api";

export default function AccountRecoveryPage() {
  const router = useRouter();

  const [patientId, setPatientId] = useState("");
  const [dob, setDob] = useState("");
  const [emergencyPhone, setEmergencyPhone] = useState("");

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleRecovery = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!patientId.trim() || !dob) {
      setErrorMsg("Please provide both Patient ID and Date of Birth.");
      return;
    }

    setLoading(true);
    try {
      // Step 1: Initiate challenge verification
      const initiateRes = await initiateRecovery({
        target_patient_id: patientId.trim().toUpperCase(),
        challenge_date_of_birth: dob,
        challenge_emergency_contact_phone: emergencyPhone.trim() || undefined,
      });

      if (initiateRes.status === "pending_institutional_approval") {
        setSuccessMsg(
          `Recovery Request Created (Ref: ${initiateRes.recovery_request_id.slice(0, 8)}...). ` +
          initiateRes.message
        );
        return;
      }

      // If secondary approval exists, complete transfer
      const verifyRes = await verifyRecovery(initiateRes.recovery_request_id);

      setSuccessMsg(
        verifyRes.message || "Account recovery complete. Your profile has been re-linked."
      );

      setTimeout(() => {
        router.push("/patient/dashboard");
      }, 2000);
    } catch (err: any) {
      setErrorMsg(
        err.message || "Recovery challenge failed. Please verify your details."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto py-10 px-4 space-y-6">
      <Link
        href="/patient/login"
        className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 transition"
      >
        <ArrowLeft className="w-3.5 h-3.5" /> Back to Sign In
      </Link>

      <div className="text-center space-y-2">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-amber-50 text-amber-600 mb-1">
          <ShieldAlert className="w-6 h-6" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Account Recovery
        </h1>
        <p className="text-sm text-slate-600">
          Changed or lost access to your registered phone number? Re-link your existing records without creating a duplicate profile.
        </p>
      </div>

      <div className="bg-white p-6 sm:p-8 rounded-2xl border border-slate-200 shadow-sm space-y-6">
        {errorMsg && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl p-3.5 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs rounded-xl p-3.5 flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleRecovery} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
              Target Patient ID *
            </label>
            <input
              type="text"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              placeholder="e.g. MED-2026-8K4F29"
              className="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-slate-900 text-sm"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
              Date of Birth (Identity Challenge) *
            </label>
            <input
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              className="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm"
              required
            />
            <p className="text-[11px] text-slate-500 mt-1">
              Must match the exact Date of Birth registered on this Patient ID.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
              Emergency Contact Phone (If previously provided)
            </label>
            <input
              type="tel"
              value={emergencyPhone}
              onChange={(e) => setEmergencyPhone(e.target.value)}
              placeholder="+91 98765 00000"
              className="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm"
            />
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg flex items-center justify-center gap-2 transition disabled:opacity-60 shadow-sm"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Verifying Challenge...
                </>
              ) : (
                <>
                  Verify Identity & Re-link Records <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </form>

        <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-200 text-xs text-slate-600">
          <strong>Security Note:</strong> Account takeover attempts are audited and permanently logged with timestamp and IP address.
        </div>
      </div>
    </div>
  );
}
