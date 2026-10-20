"use client";

import React, { useState, useEffect } from "react";
import {
  Search,
  UserCheck,
  ShieldAlert,
  FileText,
  Download,
  ExternalLink,
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
} from "lucide-react";
import {
  loginHospitalStaff,
  doctorLookupPatient,
  getHospitalStaffInfo,
  clearHospitalStaffAuth,
  HospitalStaffLoginResult,
  DoctorPatientLookupResponse,
} from "@/lib/api";

const DEMO_DOCTORS = [
  {
    email: "dr.sharma@cityhospital.org",
    password: "Password123!",
    hospital_reg: "HOSP-REG-4421",
    name: "Dr. Ananya Sharma",
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
    hospital_name: "Metro Specialty Clinic",
    badge: "Unauthorized Hospital",
    badgeColor: "bg-rose-100 text-rose-800 border-rose-300",
    description: "Has no active grant for MED-2026-3N62YU. System must strictly block access (403 Forbidden).",
  },
];

export default function HospitalLookupPage() {
  const [staff, setStaff] = useState<HospitalStaffLoginResult | null>(null);
  const [patientIdInput, setPatientIdInput] = useState<string>("MED-2026-3N62YU");
  const [loading, setLoading] = useState<boolean>(false);
  const [authLoading, setAuthLoading] = useState<boolean>(false);
  const [lookupResult, setLookupResult] = useState<DoctorPatientLookupResponse | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Manual login form state
  const [loginEmail, setLoginEmail] = useState<string>("dr.sharma@cityhospital.org");
  const [loginPassword, setLoginPassword] = useState<string>("Password123!");
  const [loginHospitalReg, setLoginHospitalReg] = useState<string>("HOSP-REG-4421");
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

  const handleQuickLogin = async (doc: typeof DEMO_DOCTORS[0]) => {
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
        email: loginEmail,
        password: loginPassword,
        hospital_registration_number: loginHospitalReg,
      });
      setStaff(result);
    } catch (err: any) {
      setLoginError(err.message || "Login failed.");
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSwitchDoctor = () => {
    clearHospitalStaffAuth();
    setStaff(null);
    setLookupResult(null);
    setErrorStatus(null);
    setErrorMessage(null);
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

  const formatFileSize = (bytes: number): string => {
    if (!bytes || bytes === 0) return "0 KB";
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(1)} MB`;
  };

  const formatCategory = (cat: string): string => {
    switch (cat) {
      case "blood_test":
        return "Blood Test";
      case "xray":
        return "X-Ray";
      case "ct_scan":
        return "CT Scan";
      case "mri":
        return "MRI";
      case "prescription":
        return "Prescription";
      case "discharge_summary":
        return "Discharge Summary";
      default:
        return "Clinical Report";
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2.5">
          <Stethoscope className="w-7 h-7 text-emerald-600" />
          Doctor Patient Record Lookup
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          Search for an existing patient using their permanent unique Patient ID to retrieve identity details and authorized medical reports.
        </p>
      </div>

      {/* Clinician Authentication Card */}
      {!staff ? (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3 text-slate-900 font-semibold">
            <Lock className="w-5 h-5 text-indigo-600" />
            <span>Clinician Verification & Institutional Access</span>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            Medical record retrieval enforces strict organization authorization. Please select a verified doctor profile or sign in with your hospital credentials to begin:
          </p>

          {/* Quick Doctor Selectors for Testing Authorization */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {DEMO_DOCTORS.map((doc) => (
              <div
                key={doc.email}
                className="p-4 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100/80 transition flex flex-col justify-between space-y-3"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm text-slate-900">{doc.name}</span>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${doc.badgeColor}`}
                    >
                      {doc.badge}
                    </span>
                  </div>
                  <div className="text-xs text-slate-600 font-mono mt-0.5 flex items-center gap-1">
                    <Building2 className="w-3.5 h-3.5 text-slate-400" />
                    {doc.hospital_name} ({doc.hospital_reg})
                  </div>
                  <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                    {doc.description}
                  </p>
                </div>

                <button
                  onClick={() => handleQuickLogin(doc)}
                  disabled={authLoading}
                  className="w-full py-2 px-3 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                >
                  {authLoading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <>
                      <span>Sign in as {doc.name.split(" ")[1]}</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </div>
            ))}
          </div>

          {/* Manual Sign-in Accordion / Form */}
          <details className="pt-2 text-xs text-slate-600 group">
            <summary className="cursor-pointer font-medium text-slate-700 hover:text-slate-900">
              Or sign in with custom hospital credentials
            </summary>
            <form onSubmit={handleManualLogin} className="mt-3 p-4 bg-slate-50 rounded-xl space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                    Doctor Email
                  </label>
                  <input
                    type="email"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    required
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-mono text-slate-900 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    required
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                    Hospital Reg Number
                  </label>
                  <input
                    type="text"
                    value={loginHospitalReg}
                    onChange={(e) => setLoginHospitalReg(e.target.value)}
                    required
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-mono text-slate-900 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
              </div>

              {loginError && (
                <div className="p-2.5 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg text-xs">
                  {loginError}
                </div>
              )}

              <button
                type="submit"
                disabled={authLoading}
                className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold transition"
              >
                {authLoading ? "Authenticating..." : "Sign In to Hospital Portal"}
              </button>
            </form>
          </details>
        </div>
      ) : (
        /* Active Clinician Banner */
        <div className="bg-emerald-900/90 text-white rounded-2xl p-4 sm:p-5 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-full bg-emerald-800 flex items-center justify-center border border-emerald-700 flex-shrink-0">
              <UserCheck className="w-6 h-6 text-emerald-300" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-base">{staff.staff_name}</span>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-emerald-800 text-emerald-200 border border-emerald-700">
                  {staff.staff_role}
                </span>
              </div>
              <div className="text-xs text-emerald-200 flex items-center gap-2 mt-0.5 font-mono">
                <span>{staff.hospital_name}</span>
                <span>•</span>
                <span>{staff.hospital_registration_number}</span>
              </div>
            </div>
          </div>

          <button
            onClick={handleSwitchDoctor}
            className="text-xs bg-emerald-800 hover:bg-emerald-700 text-emerald-100 px-3 py-1.5 rounded-lg border border-emerald-700 transition flex items-center gap-1.5"
            title="Switch clinician or hospital organization"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Switch Doctor / Hospital</span>
          </button>
        </div>
      )}

      {/* Lookup Form */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <label className="block text-sm font-semibold text-slate-800">
          Enter Patient ID (e.g., MED-YYYY-XXXXXX)
        </label>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-5 h-5 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="text"
              value={patientIdInput}
              onChange={(e) => setPatientIdInput(e.target.value.toUpperCase())}
              placeholder="MED-2026-XXXXXX"
              disabled={loading || !staff}
              className="w-full pl-11 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono text-slate-900 uppercase disabled:bg-slate-100 disabled:cursor-not-allowed"
            />
          </div>
          <button
            type="button"
            onClick={() => handleSearch()}
            disabled={loading || !staff || !patientIdInput.trim()}
            className="px-6 py-2.5 bg-slate-900 hover:bg-slate-800 text-white font-medium rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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

        {/* Quick Demo ID Chip */}
        <div className="flex items-center gap-2 pt-1">
          <span className="text-xs text-slate-500">Demo Patient:</span>
          <button
            type="button"
            onClick={() => {
              setPatientIdInput("MED-2026-3N62YU");
              if (staff) handleSearch("MED-2026-3N62YU");
            }}
            className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 transition"
          >
            MED-2026-3N62YU
          </button>
        </div>
      </div>

      {/* State: 403 Forbidden Error (Unauthorized Doctor/Hospital) */}
      {errorStatus === 403 && (
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 space-y-3">
          <div className="flex items-center gap-3 text-rose-800 font-semibold text-base">
            <ShieldAlert className="w-6 h-6 text-rose-600 flex-shrink-0" />
            <span>Access Denied: Institutional Authorization Required</span>
          </div>
          <p className="text-sm text-rose-700 leading-relaxed">
            {errorMessage ||
              "Your hospital organization is not authorized to access medical records for this patient. An active institutional access grant issued by the patient is required."}
          </p>
          <div className="bg-white/80 p-3.5 rounded-xl border border-rose-200 text-xs text-rose-900 space-y-1">
            <div className="font-semibold">Security & Privacy Protection:</div>
            <div>
              • Mere knowledge of a Patient ID does not grant record access.
            </div>
            <div>
              • Unauthorized lookup attempts are permanently logged in the audit registry.
            </div>
            <div>
              • Zero patient records or diagnostic files were transmitted.
            </div>
          </div>
        </div>
      )}

      {/* State: 404 Not Found (Invalid Patient ID) */}
      {errorStatus === 404 && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 space-y-2">
          <div className="flex items-center gap-2.5 text-amber-800 font-semibold">
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
            <span>Patient Not Found</span>
          </div>
          <p className="text-sm text-amber-700 leading-relaxed">
            {errorMessage ||
              `No patient record exists matching Patient ID '${patientIdInput}'. Please double check the ID format and try again.`}
          </p>
        </div>
      )}

      {/* State: Other Errors */}
      {errorStatus && errorStatus !== 403 && errorStatus !== 404 && (
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 text-sm text-rose-700">
          {errorMessage || "An unexpected error occurred. Please try again."}
        </div>
      )}

      {/* State: Successful Authorized Lookup */}
      {lookupResult && lookupResult.authorized && (
        <div className="space-y-6">
          {/* Patient Identity Confirmation Card */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2 text-slate-900 font-semibold">
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
                <span>Patient Identity Confirmed</span>
              </div>
              <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">
                {lookupResult.patient.patient_id}
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-slate-500 block mb-0.5">Full Name</span>
                <span className="font-semibold text-slate-900 text-sm capitalize">
                  {lookupResult.patient.full_name}
                </span>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-slate-500 block mb-0.5">Gender</span>
                <span className="font-semibold text-slate-900 text-sm capitalize">
                  {lookupResult.patient.gender}
                </span>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-slate-500 block mb-0.5">Blood Group</span>
                <span className="font-semibold text-rose-600 text-sm font-mono">
                  {lookupResult.patient.blood_group || "N/A"}
                </span>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-slate-500 block mb-0.5">Date of Birth</span>
                <span className="font-semibold text-slate-900 text-sm font-mono">
                  {lookupResult.patient.date_of_birth || "Recorded"}
                </span>
              </div>
            </div>

            <div className="text-[11px] text-slate-500 flex items-center justify-between pt-1">
              <span>
                Authorized Hospital Organization:{" "}
                <strong>{lookupResult.hospital_name}</strong>
              </span>
              <span className="text-emerald-600 font-medium flex items-center gap-1">
                <CheckCircle className="w-3.5 h-3.5" /> Institutional Access Verified
              </span>
            </div>
          </div>

          {/* Medical Reports Section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-600" />
                Available Medical Reports ({lookupResult.reports.length})
              </h2>
            </div>

            {lookupResult.reports.length === 0 ? (
              /* State: Valid ID with No Reports (Empty State) */
              <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center space-y-3">
                <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
                  <FileX className="w-6 h-6" />
                </div>
                <h3 className="font-semibold text-slate-800 text-sm">
                  No Medical Reports Available
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Patient identity has been confirmed, but no diagnostic reports or clinical records are currently on file for this patient.
                </p>
              </div>
            ) : (
              /* Reports Grid */
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {lookupResult.reports.map((report) => (
                  <div
                    key={report.report_id}
                    className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 flex flex-col justify-between hover:border-slate-300 transition space-y-3"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2">
                        <h4 className="font-semibold text-sm text-slate-900 capitalize">
                          {report.title}
                        </h4>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                          {formatCategory(report.category)}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 font-mono mt-1">
                        Report ID: {report.report_id}
                      </div>

                      <div className="mt-3 flex items-center gap-4 text-xs text-slate-600">
                        <div className="flex items-center gap-1">
                          <Calendar className="w-3.5 h-3.5 text-slate-400" />
                          <span>{report.report_date}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span>{formatFileSize(report.file_size_bytes)}</span>
                        </div>
                        {report.verification_status === "hospital_verified" && (
                          <span className="text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                            Verified
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="pt-2 border-t border-slate-100 flex gap-2">
                      {report.download_url ? (
                        <>
                          <a
                            href={report.download_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex-1 py-1.5 px-3 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                            <span>View PDF</span>
                          </a>
                          <a
                            href={report.download_url}
                            download={`${report.report_id}.pdf`}
                            className="py-1.5 px-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition border border-slate-200"
                            title="Download PDF to device"
                          >
                            <Download className="w-3.5 h-3.5" />
                            <span>Download</span>
                          </a>
                        </>
                      ) : (
                        <div className="text-xs text-slate-400 italic py-1">
                          Download link currently unavailable
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Institutional Security Notice */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-900 flex items-start gap-3">
        <ShieldAlert className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <strong>Institutional Access Policy:</strong>
          <p className="text-blue-800 leading-relaxed">
            Patient medical reports are strictly protected by Row-Level Security (RLS) and institutional access policies. Only clinicians affiliated with an organization that holds an active patient grant or issued the clinical report can view diagnostic data. All lookup transactions and access denials are cryptographically audited.
          </p>
        </div>
      </div>
    </div>
  );
}
