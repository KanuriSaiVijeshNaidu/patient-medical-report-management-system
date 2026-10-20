"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  QrCode,
  Upload,
  FileText,
  ShieldCheck,
  Copy,
  Check,
  LogOut,
  User,
  Phone,
  Calendar,
  Heart,
  AlertCircle,
  Loader2,
  RefreshCw,
  Edit2,
  Download,
  ExternalLink,
} from "lucide-react";
import {
  getMyProfile,
  updateProfile,
  getMyReports,
  getReportDownloadUrl,
  PatientProfile,
  MedicalReport,
} from "@/lib/api";
import { signOutPatient, isSupabaseConfigured } from "@/lib/supabaseClient";

export default function PatientDashboardPage() {
  const router = useRouter();

  const [profile, setProfile] = useState<PatientProfile | null>(null);
  const [recentReports, setRecentReports] = useState<MedicalReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);

  // Edit form state
  const [bloodGroup, setBloodGroup] = useState("");
  const [emergencyPhone, setEmergencyPhone] = useState("");
  const [updating, setUpdating] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await getMyProfile();
      setProfile(data);
      setBloodGroup(data.blood_group || "");
      setEmergencyPhone(data.emergency_contact_phone || "");

      // Load recent medical reports
      try {
        const reportsData = await getMyReports();
        setRecentReports((reportsData || []).slice(0, 3));
      } catch (e) {
        // If reports fails (e.g. no reports), continue
        setRecentReports([]);
      }
    } catch (err: any) {
      if (err.message?.includes("not found") || err.message?.includes("404")) {
        router.push("/register");
        return;
      }
      if (
        err.message?.includes("Authentication required") ||
        err.message?.includes("401") ||
        err.message?.includes("sign in")
      ) {
        setProfile(null);
        setRecentReports([]);
        router.push("/patient/login");
        return;
      }
      setErrorMsg(err.message || "Failed to load patient profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("med_report_token");
      if (!token || !token.trim()) {
        router.push("/patient/login");
        return;
      }
    }
    fetchData();
  }, []);

  const handleDownload = async (report: MedicalReport) => {
    setDownloadingId(report.id);
    try {
      const result = await getReportDownloadUrl(report.report_id || report.id);
      if (result.download_url) {
        window.open(result.download_url, "_blank", "noopener,noreferrer");
      }
    } catch (err: any) {
      alert(`Could not open report: ${err.message}`);
    } finally {
      setDownloadingId(null);
    }
  };

  const handleCopyId = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSignOut = async () => {
    setProfile(null);
    setRecentReports([]);
    await signOutPatient();
    router.push("/patient/login");
  };

  const handleSaveUpdates = async (e: React.FormEvent) => {
    e.preventDefault();
    setUpdating(true);
    try {
      const updated = await updateProfile({
        blood_group: bloodGroup || undefined,
        emergency_contact_phone: emergencyPhone || undefined,
      });
      setProfile(updated);
      setShowEditModal(false);
    } catch (err: any) {
      alert(err.message || "Could not update profile.");
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Top Controls Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Patient Dashboard</h1>
          <p className="text-xs text-slate-500">
            View your verified permanent identity and manage access to your medical history.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchData}
            className="p-2 text-slate-600 hover:text-blue-600 rounded-lg hover:bg-slate-100 transition"
            title="Refresh profile and records"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-3">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
          <p className="text-sm text-slate-600">Retrieving authenticated patient profile...</p>
        </div>
      ) : errorMsg ? (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-amber-900 space-y-3">
          <div className="flex items-center gap-2 font-semibold">
            <AlertCircle className="w-5 h-5 text-amber-600" /> Authentication Session Notice
          </div>
          <p className="text-xs text-amber-800 leading-relaxed">{errorMsg}</p>
          <div className="pt-2 flex flex-wrap gap-3">
            <Link
              href="/patient/login"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition"
            >
              Sign In
            </Link>
            <Link
              href="/patient/register"
              className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-medium transition"
            >
              Create Account
            </Link>
          </div>
        </div>
      ) : profile ? (
        <>
          {/* Patient Identity Card */}
          <div className="bg-gradient-to-r from-blue-700 via-blue-600 to-indigo-700 rounded-2xl p-6 sm:p-8 text-white shadow-md flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/20 text-xs font-medium backdrop-blur-sm">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-300" />
                <span>Verification: {profile.verification_status}</span>
              </div>
              <h2 className="text-2xl sm:text-3xl font-extrabold">{profile.full_name}</h2>
              <div className="flex flex-wrap gap-4 text-xs text-blue-100">
                <span className="flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5" /> Born: {profile.date_of_birth}
                </span>
                <span className="flex items-center gap-1">
                  <User className="w-3.5 h-3.5" /> Gender: {profile.gender}
                </span>
                {profile.blood_group && (
                  <span className="flex items-center gap-1">
                    <Heart className="w-3.5 h-3.5 text-rose-300" /> Blood Group: {profile.blood_group}
                  </span>
                )}
                {profile.phone_masked && (
                  <span className="flex items-center gap-1">
                    <Phone className="w-3.5 h-3.5" /> Phone: {profile.phone_masked}
                  </span>
                )}
              </div>
            </div>

            {/* Permanent Patient ID Highlight Box */}
            <div className="bg-white/10 backdrop-blur-md border border-white/25 rounded-2xl p-5 text-center min-w-[260px] space-y-2">
              <span className="text-[11px] uppercase tracking-wider text-blue-200 font-semibold block">
                Permanent Patient ID
              </span>
              <div className="flex items-center justify-center gap-2">
                <span className="text-2xl font-mono font-bold tracking-wider">
                  {profile.patient_id}
                </span>
                <button
                  onClick={() => handleCopyId(profile.patient_id)}
                  className="p-1.5 rounded-lg bg-white/20 hover:bg-white/30 transition text-white"
                  title="Copy Patient ID"
                >
                  {copied ? <Check className="w-4 h-4 text-emerald-300" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
              <span className="text-[11px] text-blue-200 block">
                {copied ? "Copied to clipboard!" : "Present at hospital registration"}
              </span>
            </div>
          </div>

          {/* Quick Action Cards */}
          <div className="grid sm:grid-cols-3 gap-4">
            <Link
              href="/patient/upload"
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:border-blue-400 transition group"
            >
              <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center mb-3 group-hover:scale-105 transition">
                <Upload className="w-5 h-5" />
              </div>
              <h3 className="font-semibold text-slate-900 text-sm">Upload New Report</h3>
              <p className="text-xs text-slate-500 mt-1">Upload blood tests, MRI scans, X-rays, or prescriptions.</p>
            </Link>

            <Link
              href="/patient/share"
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:border-blue-400 transition group"
            >
              <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center mb-3 group-hover:scale-105 transition">
                <QrCode className="w-5 h-5" />
              </div>
              <h3 className="font-semibold text-slate-900 text-sm">Create Share QR</h3>
              <p className="text-xs text-slate-500 mt-1">Generate a time-bound, revocable link for doctor review.</p>
            </Link>

            <Link
              href="/patient/reports"
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:border-blue-400 transition group"
            >
              <div className="w-10 h-10 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center mb-3 group-hover:scale-105 transition">
                <FileText className="w-5 h-5" />
              </div>
              <h3 className="font-semibold text-slate-900 text-sm">Medical Library</h3>
              <p className="text-xs text-slate-500 mt-1">View categorized history and lab-verified records.</p>
            </Link>
          </div>

          {/* Recent Medical Records Widget */}
          <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="font-bold text-slate-900 text-base">Recent Medical Reports</h3>
                <p className="text-xs text-slate-500">Your latest uploaded diagnostic records and test results.</p>
              </div>
              <Link
                href="/reports"
                className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                View All Records <ExternalLink className="w-3.5 h-3.5" />
              </Link>
            </div>

            {recentReports.length === 0 ? (
              <div className="text-center py-6 space-y-2">
                <FileText className="w-8 h-8 text-slate-300 mx-auto" />
                <p className="text-xs text-slate-500">No medical reports recorded yet.</p>
                <Link
                  href="/upload"
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-50 text-blue-600 text-xs font-semibold hover:bg-blue-100 transition"
                >
                  <Upload className="w-3 h-3" /> Upload Your First Report
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {recentReports.map((report) => (
                  <div
                    key={report.id}
                    className="py-3 flex items-center justify-between gap-4 first:pt-0 last:pb-0"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0">
                        <FileText className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-slate-900 truncate">{report.title}</p>
                        <p className="text-[11px] text-slate-500">
                          {report.report_id} • {report.report_date} • {report.category.replace("_", " ")}
                        </p>
                      </div>
                    </div>

                    <button
                      onClick={() => handleDownload(report)}
                      disabled={downloadingId === report.id}
                      className="px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-blue-50 text-slate-700 hover:text-blue-700 text-xs font-semibold transition border border-slate-200 flex items-center gap-1.5 flex-shrink-0 disabled:opacity-60"
                      title="View PDF"
                    >
                      {downloadingId === report.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Download className="w-3 h-3" />
                      )}
                      <span>View</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Account Profile Management Section */}
          <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-slate-900 text-base">Account & Identity Details</h3>
              <button
                onClick={() => setShowEditModal(true)}
                className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                <Edit2 className="w-3.5 h-3.5" /> Edit Clinical Info
              </button>
            </div>

            <div className="grid sm:grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-slate-500 block">Registered Name</span>
                <span className="font-semibold text-slate-800 text-sm">{profile.full_name}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Date of Birth</span>
                <span className="font-semibold text-slate-800 text-sm">{profile.date_of_birth}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Blood Group</span>
                <span className="font-semibold text-slate-800 text-sm">{profile.blood_group || "Not specified"}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Emergency Contact</span>
                <span className="font-semibold text-slate-800 text-sm">{profile.emergency_contact_phone || "Not specified"}</span>
              </div>
            </div>

            <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Account created on: {new Date(profile.created_at).toLocaleDateString()}</span>
              <Link href="/patient/recovery" className="text-blue-600 hover:underline">
                Changed phone number? Re-link records
              </Link>
            </div>
          </div>
        </>
      ) : null}

      {/* Edit Clinical Info Modal */}
      {showEditModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4 border border-slate-200">
            <h3 className="text-lg font-bold text-slate-900">Edit Clinical Details</h3>
            <form onSubmit={handleSaveUpdates} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                  Blood Group
                </label>
                <select
                  value={bloodGroup}
                  onChange={(e) => setBloodGroup(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white"
                >
                  <option value="">Unknown / Not Tested</option>
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

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                  Emergency Contact Phone
                </label>
                <input
                  type="tel"
                  value={emergencyPhone}
                  onChange={(e) => setEmergencyPhone(e.target.value)}
                  placeholder="+91 98765 00000"
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updating}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition disabled:opacity-60"
                >
                  {updating ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
