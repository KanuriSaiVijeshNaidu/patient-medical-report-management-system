"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Search,
  UserCheck,
  ShieldAlert,
  FileText,
  Download,
  Calendar,
  Building2,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Lock,
  Stethoscope,
  ArrowRight,
  User,
  ShieldCheck,
  FileX,
  Copy,
  Check,
  Eye,
  Mail,
  EyeOff,
  FlaskConical,
  Scan,
  Aperture,
  Brain,
  Pill,
  Heart,
  ChevronRight,
  FolderOpen,
} from "lucide-react";
import {
  loginHospitalStaff,
  doctorLookupPatient,
  getHospitalStaffInfo,
  clearHospitalStaffAuth,
  HospitalStaffLoginResult,
  DoctorPatientLookupResponse,
  SharedReportItem,
} from "@/lib/api";

const DEMO_DOCTORS = [
  {
    email: "dr.sharma@cityhospital.org",
    password: "Password123!",
    hospital_reg: "HOSP-REG-4421",
    name: "Dr. Ananya Sharma",
    role: "Consultant Physician",
    hospital_name: "City General Hospital",
    badge: "Authorized Hospital",
    badgeColor: "bg-emerald-100 text-emerald-800 border-emerald-300",
    description: "Holds active institutional access grant for demo patient MED-2026-3N62YU.",
  },
  {
    email: "dr.patel@metroclinic.org",
    password: "Password123!",
    hospital_reg: "HOSP-REG-9999",
    name: "Dr. Rajesh Patel",
    role: "Consultant Cardiologist",
    hospital_name: "Metro Specialty Clinic",
    badge: "Unauthorized Hospital",
    badgeColor: "bg-rose-100 text-rose-800 border-rose-300",
    description: "Has no active grant for MED-2026-3N62YU. System must strictly block access (403 Forbidden).",
  },
];

export default function DoctorPatientLookupPage() {
  const [staff, setStaff] = useState<HospitalStaffLoginResult | null>(null);
  const [patientIdInput, setPatientIdInput] = useState<string>("MED-2026-3N62YU");
  const [loading, setLoading] = useState<boolean>(false);
  const [authLoading, setAuthLoading] = useState<boolean>(false);
  const [lookupResult, setLookupResult] = useState<DoctorPatientLookupResponse | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState(false);

  // Manual sign-in states for unauthenticated view
  const [loginEmail, setLoginEmail] = useState("dr.sharma@cityhospital.org");
  const [loginPassword, setLoginPassword] = useState("Password123!");
  const [loginHospitalReg, setLoginHospitalReg] = useState("HOSP-REG-4421");
  const [showPassword, setShowPassword] = useState(false);
  const [keepSignedIn, setKeepSignedIn] = useState(true);
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    const updateStaff = () => {
      setStaff(getHospitalStaffInfo());
    };

    updateStaff();
    window.addEventListener("hospital-auth-change", updateStaff);
    window.addEventListener("storage", updateStaff);

    return () => {
      window.removeEventListener("hospital-auth-change", updateStaff);
      window.removeEventListener("storage", updateStaff);
    };
  }, []);

  const handleQuickLogin = async (doc: (typeof DEMO_DOCTORS)[0]) => {
    setAuthLoading(true);
    setLoginError(null);
    setLookupResult(null);
    setErrorStatus(null);
    setErrorMessage(null);

    try {
      const result = await loginHospitalStaff({
        email: doc.email,
        password: doc.password,
        hospital_registration_number: doc.hospital_reg,
      });
      setStaff(result);
    } catch (err: any) {
      setLoginError(err.message || "Failed to sign in doctor.");
    } finally {
      setAuthLoading(false);
    }
  };

  const handleManualLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    setLoginError(null);
    try {
      const result = await loginHospitalStaff({
        email: loginEmail.trim(),
        password: loginPassword,
        hospital_registration_number: loginHospitalReg.trim(),
      });
      setStaff(result);
    } catch (err: any) {
      setLoginError(err.message || "Login failed.");
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSearch = async (overrideId?: string) => {
    const targetId = (overrideId || patientIdInput).trim().toUpperCase();
    if (!targetId) {
      setErrorStatus(400);
      setErrorMessage("Please enter a valid Patient ID.");
      return;
    }

    setLoading(true);
    setErrorStatus(null);
    setErrorMessage(null);
    setLookupResult(null);

    try {
      const data = await doctorLookupPatient(targetId);
      setLookupResult(data);
    } catch (err: any) {
      setErrorStatus(err.status || 500);
      setErrorMessage(
        err.detail || err.message || "An error occurred while looking up patient records."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleCopyPatientId = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  const getReportCategoryStyle = (cat: string) => {
    switch (cat) {
      case "blood_test":
        return {
          icon: FlaskConical,
          bg: "bg-rose-50 text-rose-500 border-rose-100",
          title: "Laboratory Results",
        };
      case "xray":
      case "ct_scan":
        return {
          icon: Scan,
          bg: "bg-emerald-50 text-emerald-600 border-emerald-100",
          title: "Radiology Reports",
        };
      case "mri":
        return {
          icon: Brain,
          bg: "bg-purple-50 text-purple-600 border-purple-100",
          title: "MRI Scans",
        };
      case "prescription":
        return {
          icon: Pill,
          bg: "bg-amber-50 text-amber-600 border-amber-100",
          title: "Prescription",
        };
      default:
        return {
          icon: FileText,
          bg: "bg-blue-50 text-blue-600 border-blue-100",
          title: "Clinical Summary",
        };
    }
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "Recorded";
    try {
      return new Date(dateStr).toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  // ---------------------------------------------------------------------------
  // IF NOT SIGNED IN: RENDER PAGE 4 (CLINICIAN SIGN IN)
  // ---------------------------------------------------------------------------
  if (!staff) {
    return (
      <div className="min-h-[80vh] flex items-center justify-center p-4 py-8 animate-in fade-in duration-300">
        <div className="max-w-md w-full bg-white rounded-3xl p-6 sm:p-8 border border-slate-200/90 shadow-xl space-y-6">
          {/* Top Medical Cross Circle Emblem */}
          <div className="text-center space-y-3">
            <div className="w-14 h-14 rounded-full bg-emerald-600 text-white flex items-center justify-center mx-auto shadow-md shadow-emerald-600/20">
              <span className="text-2xl font-bold font-mono">+</span>
            </div>

            <div>
              <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
                Clinician Sign In
              </h1>
              <p className="text-xs text-slate-500 mt-1 max-w-xs mx-auto">
                Access the hospital's medical records portal for care teams and authorized staff only.
              </p>
            </div>
          </div>

          {/* Login Error Alert */}
          {loginError && (
            <div className="p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2.5">
              <AlertTriangle className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{loginError}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleManualLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Hospital Email or Username
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="text"
                  required
                  placeholder="Enter your hospital email or username"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 text-xs sm:text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder="Enter your password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  className="w-full pl-10 pr-10 py-2.5 rounded-xl border border-slate-200 text-xs sm:text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Keep me signed in */}
            <div className="flex items-center justify-between text-xs pt-1">
              <label className="flex items-center gap-2 text-slate-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={keepSignedIn}
                  onChange={(e) => setKeepSignedIn(e.target.checked)}
                  className="rounded text-blue-600 focus:ring-0"
                />
                <span>Keep me signed in on this device</span>
              </label>
            </div>
            <p className="text-[10px] text-slate-400 pl-6">
              Only use on a trusted, secure device.
            </p>

            {/* Primary Sign In Button */}
            <button
              type="submit"
              disabled={authLoading}
              className="w-full py-3 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-sm font-bold transition flex items-center justify-center gap-2 shadow-md disabled:opacity-60"
            >
              {authLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Authenticating Clinician...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="relative flex items-center justify-center">
            <div className="border-t border-slate-200 w-full" />
            <span className="bg-white px-3 text-[11px] text-slate-400 font-medium uppercase">
              or
            </span>
          </div>

          {/* One-click Verified Demo Clinicians Selector */}
          <div className="space-y-2">
            <span className="block text-[11px] font-semibold text-slate-500 text-center">
              Quick Clinician Select for Demonstration
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {DEMO_DOCTORS.map((doc) => (
                <button
                  key={doc.email}
                  type="button"
                  onClick={() => handleQuickLogin(doc)}
                  disabled={authLoading}
                  className="p-2.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-blue-50 hover:border-blue-300 text-left transition group"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-800 group-hover:text-blue-700">
                      {doc.name.split(" ")[1]}
                    </span>
                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${doc.badgeColor}`}>
                      {doc.badge.split(" ")[0]}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500 block truncate mt-0.5 font-mono">
                    {doc.hospital_name}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Authorized Access Notice Footer */}
          <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200/80 text-[11px] text-slate-600 space-y-1">
            <div className="flex items-center gap-1.5 font-bold text-slate-800">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>Authorized Access Only</span>
            </div>
            <p className="leading-relaxed text-slate-500 text-[10px]">
              This system contains confidential patient information. Access is restricted to authorized hospital staff. All activity is monitored and may be audited.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // IF SIGNED IN: RENDER PAGE 5 (DOCTOR PATIENT RECORD LOOKUP)
  // ---------------------------------------------------------------------------
  return (
    <div className="space-y-6 sm:space-y-7 animate-in fade-in duration-300">
      {/* Page Heading */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
          Doctor Patient Record Lookup
        </h1>
        <p className="text-sm text-slate-500 mt-1 max-w-3xl leading-relaxed">
          Search for a patient's medical records using their unique hospital patient ID. Access is restricted to authorised clinicians and is monitored for security and governance purposes.
        </p>
      </div>

      {/* Clinician Status Banners (Screen 5 top banners) */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
        {/* Left Status: Authorised Clinician — Access Granted */}
        <div className="md:col-span-8 bg-white rounded-2xl p-4 sm:p-5 border border-slate-200/80 shadow-sm flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-full bg-emerald-500 text-white flex items-center justify-center flex-shrink-0 shadow-sm">
            <Check className="w-5 h-5 stroke-[3]" />
          </div>
          <div className="min-w-0">
            <h3 className="font-bold text-slate-900 text-sm sm:text-base">
              Authorised Clinician — Access Granted
            </h3>
            <p className="text-xs text-slate-500 truncate mt-0.5">
              You are signed in as{" "}
              <strong className="text-slate-700">{staff.staff_name}</strong>{" "}
              | Consultant Physician | {staff.hospital_name}
            </p>
          </div>
        </div>

        {/* Right Status: Institutional Access Verified */}
        <div className="md:col-span-4 bg-white rounded-2xl p-4 sm:p-5 border border-slate-200/80 shadow-sm flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center flex-shrink-0 border border-emerald-200">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-bold text-slate-800 block">
                Institutional Access Verified
              </span>
              <span className="text-xs text-slate-500 font-mono">
                {staff.hospital_name}
              </span>
            </div>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400" />
        </div>
      </div>

      {/* Patient ID Lookup Card */}
      <div className="bg-white rounded-3xl p-6 sm:p-7 border border-slate-200/80 shadow-sm space-y-4">
        <div className="flex items-center gap-2.5 text-blue-600">
          <Search className="w-5 h-5" />
          <h2 className="text-base font-bold text-slate-900">Patient ID Lookup</h2>
        </div>
        <p className="text-xs text-slate-500">
          Enter the patient's unique hospital ID to retrieve their medical records.
        </p>

        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <User className="w-4 h-4 text-slate-400 absolute left-4 top-3.5" />
            <input
              type="text"
              placeholder="MED-••••-••••"
              value={patientIdInput}
              onChange={(e) => setPatientIdInput(e.target.value.toUpperCase())}
              className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 text-sm font-mono text-slate-900 uppercase tracking-wider placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition"
            />
          </div>

          <button
            type="button"
            onClick={() => handleSearch()}
            disabled={loading || !patientIdInput.trim()}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs sm:text-sm font-bold transition flex items-center justify-center gap-2 shadow-sm disabled:opacity-50"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Searching...</span>
              </>
            ) : (
              <>
                <Search className="w-4 h-4" />
                <span>Search Record</span>
              </>
            )}
          </button>
        </div>

        {/* Format note & quick demo button */}
        <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-400 pt-1">
          <span>Format: MED-XXXX-XXXX (e.g., MED-2026-3N62YU)</span>
          <div className="flex items-center gap-1.5 mt-1 sm:mt-0">
            <span className="text-slate-500">Quick Test ID:</span>
            <button
              type="button"
              onClick={() => {
                setPatientIdInput("MED-2026-3N62YU");
                handleSearch("MED-2026-3N62YU");
              }}
              className="px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 font-mono font-medium hover:bg-blue-100 border border-blue-200 transition"
            >
              MED-2026-3N62YU
            </button>
          </div>
        </div>
      </div>

      {/* State: 403 Forbidden Access Denied (Unauthorized Doctor / Hospital) */}
      {errorStatus === 403 && (
        <div className="bg-rose-50 border border-rose-200 rounded-3xl p-6 sm:p-7 space-y-4 animate-in fade-in">
          <div className="flex items-center gap-3 text-rose-800 font-bold text-base">
            <ShieldAlert className="w-6 h-6 text-rose-600 flex-shrink-0" />
            <span>Access Denied: Institutional Authorization Required</span>
          </div>
          <p className="text-sm text-rose-700 leading-relaxed">
            {errorMessage ||
              "Your hospital organization is not authorized to access medical records for this patient. An active institutional access grant issued by the patient is required."}
          </p>
          <div className="bg-white/80 p-4 rounded-2xl border border-rose-200 text-xs text-rose-950 space-y-1.5 font-medium">
            <div className="font-bold">Security & Governance Protections:</div>
            <div>• Knowing a Patient ID does not grant record access.</div>
            <div>• Unauthorized lookup attempts are permanently logged in the audit registry.</div>
            <div>• Zero patient medical reports or diagnostic files were exposed.</div>
          </div>
        </div>
      )}

      {/* State: 404 Not Found (Invalid Patient ID) */}
      {errorStatus === 404 && (
        <div className="bg-amber-50 border border-amber-200 rounded-3xl p-6 space-y-2 animate-in fade-in">
          <div className="flex items-center gap-2.5 text-amber-800 font-bold">
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
            <span>Patient Not Found</span>
          </div>
          <p className="text-sm text-amber-700 leading-relaxed">
            {errorMessage ||
              `No patient record exists matching Patient ID '${patientIdInput}'. Please double check the ID format and try again.`}
          </p>
        </div>
      )}

      {/* State: Successful Authorized Lookup Results */}
      {lookupResult && lookupResult.authorized && (
        <div className="space-y-6 animate-in fade-in duration-200">
          {/* Patient Identity Confirmed Card (Screen 5 format) */}
          <div className="bg-white rounded-3xl border border-slate-200/80 shadow-sm p-6 sm:p-7 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0">
                  <User className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base">
                    Patient Identity Confirmed
                  </h3>
                  <p className="text-xs text-slate-500">
                    The patient record below matches the requested ID and is available for authorised clinical access.
                  </p>
                </div>
              </div>

              {/* Right institutional verified badge */}
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold self-start sm:self-auto">
                <Check className="w-3.5 h-3.5 text-emerald-600 stroke-[3]" />
                <span>Institutional Access Verified</span>
              </div>
            </div>

            {/* 5 Column Grid for Confirmed Patient Details */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 text-xs">
              {/* Patient ID */}
              <div>
                <span className="text-[11px] text-slate-400 block font-medium mb-1">
                  Patient ID
                </span>
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-slate-900 font-mono text-sm">
                    {lookupResult.patient.patient_id}
                  </span>
                  <button
                    onClick={() => handleCopyPatientId(lookupResult.patient.patient_id)}
                    className="p-1 text-slate-400 hover:text-slate-600 rounded transition"
                    title="Copy Patient ID"
                  >
                    {copiedId ? (
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-600 mt-1">
                  <Check className="w-2.5 h-2.5 stroke-[3]" /> Identity Confirmed
                </span>
              </div>

              {/* Date of Birth */}
              <div>
                <span className="text-[11px] text-slate-400 block font-medium mb-1">
                  Date of Birth
                </span>
                <span className="font-bold text-slate-900 text-sm font-mono block">
                  {formatDate(lookupResult.patient.date_of_birth)}
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block">
                  (Age group: Adult)
                </span>
              </div>

              {/* Gender */}
              <div>
                <span className="text-[11px] text-slate-400 block font-medium mb-1">
                  Gender
                </span>
                <span className="font-bold text-slate-900 text-sm capitalize block">
                  {lookupResult.patient.gender || "Not Specified"}
                </span>
              </div>

              {/* Blood Group / Phone */}
              <div>
                <span className="text-[11px] text-slate-400 block font-medium mb-1">
                  Blood Group
                </span>
                <span className="font-bold text-rose-600 text-sm font-mono block">
                  {lookupResult.patient.blood_group || "B+"}
                </span>
              </div>

              {/* Registered Hospital */}
              <div>
                <span className="text-[11px] text-slate-400 block font-medium mb-1">
                  Registered Hospital
                </span>
                <span className="font-bold text-slate-900 text-xs block truncate">
                  {lookupResult.hospital_name}
                </span>
              </div>
            </div>
          </div>

          {/* Available Medical Reports Section (Screen 5 Grid) */}
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <FolderOpen className="w-5 h-5 text-blue-600" />
              <div>
                <h3 className="font-bold text-slate-900 text-base">
                  Available Medical Reports ({lookupResult.reports.length})
                </h3>
                <p className="text-xs text-slate-500">
                  The following reports are available for this patient. Access is limited to authorised clinical use only.
                </p>
              </div>
            </div>

            {lookupResult.reports.length === 0 ? (
              <div className="bg-white rounded-3xl border border-slate-200/80 p-10 text-center space-y-2 shadow-sm">
                <FileX className="w-8 h-8 text-slate-300 mx-auto" />
                <h4 className="font-bold text-slate-800 text-sm">No Reports On File</h4>
                <p className="text-xs text-slate-500">
                  Patient identity was confirmed, but no medical documents are currently associated with this patient record.
                </p>
              </div>
            ) : (
              /* Report Cards Grid (Matching Screen 5 5-card horizontal/grid layout) */
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {lookupResult.reports.map((report) => {
                  const style = getReportCategoryStyle(report.category);
                  const CategoryIcon = style.icon;

                  return (
                    <div
                      key={report.report_id}
                      className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-sm hover:border-slate-300 transition flex flex-col justify-between space-y-4"
                    >
                      <div className="space-y-3">
                        {/* Icon and Category Title */}
                        <div className="flex items-start gap-3">
                          <div
                            className={`w-10 h-10 rounded-xl ${style.bg} flex items-center justify-center flex-shrink-0 border`}
                          >
                            <CategoryIcon className="w-5 h-5" />
                          </div>
                          <div className="min-w-0">
                            <h4 className="font-bold text-slate-900 text-sm truncate">
                              {report.title}
                            </h4>
                            <p className="text-[11px] text-slate-400 font-mono mt-0.5 truncate">
                              Report ID: {report.report_id}
                            </p>
                          </div>
                        </div>

                        <div className="text-[11px] text-slate-500 flex items-center justify-between pt-1">
                          <span>Updated: {formatDate(report.report_date)}</span>
                          <span className="font-semibold text-slate-700">
                            {report.file_size_bytes
                              ? `${Math.round(report.file_size_bytes / 1024)} KB`
                              : "PDF"}
                          </span>
                        </div>
                      </div>

                      {/* View & Download Buttons Side-by-Side */}
                      <div className="pt-3 border-t border-slate-100 grid grid-cols-2 gap-2">
                        {report.download_url ? (
                          <>
                            <a
                              href={report.download_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="py-2 px-3 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold transition flex items-center justify-center gap-1.5"
                            >
                              <Eye className="w-3.5 h-3.5" />
                              <span>View</span>
                            </a>
                            <a
                              href={report.download_url}
                              download={`${report.report_id}.pdf`}
                              className="py-2 px-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition flex items-center justify-center gap-1.5 shadow-sm"
                            >
                              <Download className="w-3.5 h-3.5" />
                              <span>Download</span>
                            </a>
                          </>
                        ) : (
                          <div className="col-span-2 text-center text-xs text-slate-400 py-1">
                            Link unavailable
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
