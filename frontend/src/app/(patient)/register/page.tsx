"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  UserPlus,
  User,
  Lock,
  Phone,
  Mail,
  Calendar,
  AlertCircle,
  Loader2,
  ArrowRight,
  CheckCircle2,
  Copy,
  Check,
  ShieldCheck,
} from "lucide-react";
import { registerPatient, PatientRegisterInput } from "@/lib/api";

export default function PatientRegisterPage() {
  const router = useRouter();

  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [gender, setGender] = useState<"male" | "female" | "other" | "prefer_not_to_say">("prefer_not_to_say");
  const [phone, setPhone] = useState("");
  const [bloodGroup, setBloodGroup] = useState<string>("");
  const [dob, setDob] = useState("");
  const [email, setEmail] = useState("");

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [registeredResult, setRegisteredResult] = useState<{
    patient_id: string;
    full_name: string;
    username: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const todayStr = new Date().toISOString().split("T")[0];

  const handleCopyId = () => {
    if (registeredResult?.patient_id) {
      navigator.clipboard.writeText(registeredResult.patient_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    // Frontend validation
    if (fullName.trim().length < 2) {
      setErrorMsg("Full name must be at least 2 characters.");
      return;
    }

    const cleanUsername = username.trim().toLowerCase();
    if (!/^[a-zA-Z0-9_.-]{3,30}$/.test(cleanUsername)) {
      setErrorMsg("Username must be 3-30 characters and can only contain letters, numbers, underscores, and hyphens.");
      return;
    }

    if (password.length < 8) {
      setErrorMsg("Password must be at least 8 characters long.");
      return;
    }

    const hasLetter = /[a-zA-Z]/.test(password);
    const hasDigitOrSpecial = /[0-9!@#$%^&*()_+\-=\[\]{};':",.<>?/\\|]/.test(password);
    if (!hasLetter || !hasDigitOrSpecial) {
      setErrorMsg("Password must contain at least one letter and at least one number or special character.");
      return;
    }

    const cleanedPhone = phone.trim();
    const digitsOnly = cleanedPhone.replace(/\D/g, "");
    if (digitsOnly.length < 7 || digitsOnly.length > 15) {
      setErrorMsg("Please enter a valid phone number with country code (e.g. +91 98765 43210).");
      return;
    }

    if (!bloodGroup) {
      setErrorMsg("Please select your blood group.");
      return;
    }

    if (!dob) {
      setErrorMsg("Please select your date of birth.");
      return;
    }

    if (dob > todayStr) {
      setErrorMsg("Date of birth cannot be in the future.");
      return;
    }

    const cleanEmail = email.trim().toLowerCase();
    if (cleanEmail) {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(cleanEmail)) {
        setErrorMsg("Please enter a valid email address format (e.g. name@example.com), or leave it empty.");
        return;
      }
    }

    setLoading(true);
    try {
      const payload: PatientRegisterInput = {
        full_name: fullName.trim(),
        username: cleanUsername,
        password,
        gender,
        phone: cleanedPhone,
        blood_group: bloodGroup,
        date_of_birth: dob,
        email: cleanEmail || undefined,
      };

      const res = await registerPatient(payload);
      setRegisteredResult({
        patient_id: res.patient_id,
        full_name: res.full_name,
        username: res.username,
      });
    } catch (err: any) {
      setErrorMsg(err.message || "Registration failed. Please check your details.");
    } finally {
      setLoading(false);
    }
  };

  // Post-Registration Success View: Display permanent Patient ID & Copy button
  if (registeredResult) {
    return (
      <div className="max-w-lg mx-auto py-12 px-4 space-y-6">
        <div className="bg-white p-8 rounded-2xl border border-slate-200 shadow-sm text-center space-y-6">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-50 text-emerald-600 mx-auto">
            <CheckCircle2 className="w-8 h-8" />
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-bold text-slate-900">
              Registration Complete!
            </h1>
            <p className="text-sm text-slate-600">
              Welcome, <span className="font-semibold text-slate-800">{registeredResult.full_name}</span>. Your account has been created.
            </p>
          </div>

          {/* Patient ID Display Card */}
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-center space-y-3">
            <span className="text-[11px] font-bold uppercase tracking-wider text-blue-700 block">
              Permanent Unique Patient ID
            </span>
            <div className="font-mono text-2xl sm:text-3xl font-extrabold text-blue-950 tracking-wider">
              {registeredResult.patient_id}
            </div>
            <button
              onClick={handleCopyId}
              type="button"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-blue-300 text-blue-700 hover:bg-blue-100 text-xs font-semibold transition shadow-xs"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-600" /> Copied!
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" /> Copy Patient ID
                </>
              )}
            </button>
          </div>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-600 text-left space-y-1.5">
            <div className="font-semibold flex items-center gap-1.5 text-slate-800">
              <ShieldCheck className="w-4 h-4 text-blue-600" /> Important Record Identifier
            </div>
            <p>
              Your Patient ID is permanent and collision-resistant. Clinicians and diagnostic laboratories use this identifier to search for and verify your medical records.
            </p>
          </div>

          <button
            onClick={() => router.push("/patient/dashboard")}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg flex items-center justify-center gap-2 transition shadow-sm"
          >
            Continue to Patient Dashboard <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto py-8 px-4 space-y-6">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 mb-1">
          <UserPlus className="w-6 h-6" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Patient Account Registration
        </h1>
        <p className="text-sm text-slate-600">
          Create your account with a unique username and password. A permanent unique Patient ID will be generated upon registration.
        </p>
      </div>

      <div className="bg-white p-6 sm:p-8 rounded-2xl border border-slate-200 shadow-sm space-y-6">
        {errorMsg && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl p-3.5 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span className="flex-1">{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Full Name */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
              Full Legal Name *
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Ramesh Kumar"
              className="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm"
              required
            />
          </div>

          {/* Username & Password Grid */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                Username *
              </label>
              <div className="relative">
                <User className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. ramesh_k"
                  autoCapitalize="none"
                  autoCorrect="off"
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm"
                  required
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Unique username (3-30 characters).
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                Password *
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min 8 characters"
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm"
                  required
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Letters + numbers or symbols.
              </p>
            </div>
          </div>

          {/* Date of Birth & Gender Grid */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                Date of Birth *
              </label>
              <div className="relative">
                <Calendar className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                <input
                  type="date"
                  value={dob}
                  onChange={(e) => setDob(e.target.value)}
                  max={todayStr}
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm bg-white"
                  required
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Used for clinical records & verification.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                Gender *
              </label>
              <select
                value={gender}
                onChange={(e: any) => setGender(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm bg-white"
                required
              >
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
                <option value="prefer_not_to_say">Prefer not to say</option>
              </select>
            </div>
          </div>

          {/* Phone Number & Blood Group Grid */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                Phone Number (with Country Code) *
              </label>
              <div className="relative">
                <Phone className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="e.g. +91 98765 43210"
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm"
                  required
                />
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                e.g. +91 for India.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                Blood Group *
              </label>
              <select
                value={bloodGroup}
                onChange={(e) => setBloodGroup(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm bg-white"
                required
              >
                <option value="">Select Blood Group</option>
                <option value="A+">A+</option>
                <option value="A-">A-</option>
                <option value="B+">B+</option>
                <option value="B-">B-</option>
                <option value="AB+">AB+</option>
                <option value="AB-">AB-</option>
                <option value="O+">O+</option>
                <option value="O-">O-</option>
              </select>
            </div>
          </div>

          {/* Email Address (Optional) */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                Email Address
              </label>
              <span className="text-[11px] text-slate-400 font-medium">Optional</span>
            </div>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. yourname@example.com (optional)"
                className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 text-sm"
              />
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              Optional notification email for report updates.
            </p>
          </div>

          <div className="pt-3">
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg flex items-center justify-center gap-2 transition disabled:opacity-60 shadow-sm"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Registering & Generating Patient ID...
                </>
              ) : (
                <>
                  Create Account & Generate Patient ID <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </form>

        <div className="border-t border-slate-100 pt-4 text-center">
          <p className="text-xs text-slate-600">
            Already registered?{" "}
            <Link href="/patient/login" className="text-blue-600 font-semibold hover:underline">
              Sign In
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
