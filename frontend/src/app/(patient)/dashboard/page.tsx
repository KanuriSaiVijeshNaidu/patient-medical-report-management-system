"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  UploadCloud,
  QrCode,
  BookOpen,
  FileText,
  ShieldCheck,
  Copy,
  Check,
  Calendar,
  User,
  MapPin,
  Mail,
  Phone,
  RefreshCw,
  Edit2,
  Download,
  ArrowRight,
  ExternalLink,
  Loader2,
  AlertCircle,
  FileCheck,
  Activity,
  Heart,
  Shield,
  Lock,
} from "lucide-react";
import {
  getMyProfile,
  updateProfile,
  getMyReports,
  getReportDownloadUrl,
  PatientProfile,
  MedicalReport,
} from "@/lib/api";
import { formatDateOnly } from "@/lib/utils";

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
  const [editDob, setEditDob] = useState("");
  const [updating, setUpdating] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await getMyProfile();
      setProfile(data);
      setBloodGroup(data.blood_group || "");
      setEmergencyPhone(data.emergency_contact_phone || "");
      setEditDob(data.date_of_birth || "");

      // Load recent medical reports
      try {
        const reportsData = await getMyReports();
        setRecentReports((reportsData || []).slice(0, 4));
      } catch {
        setRecentReports([]);
      }
    } catch (err: any) {
      if (err.message?.includes("not found") || err.message?.includes("404")) {
        router.push("/patient/register");
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

  const handleSaveUpdates = async (e: React.FormEvent) => {
    e.preventDefault();
    setUpdating(true);
    try {
      const updated = await updateProfile({
        blood_group: bloodGroup || undefined,
        emergency_contact_phone: emergencyPhone || undefined,
        date_of_birth: editDob || undefined,
      });
      setProfile(updated);
      setShowEditModal(false);
    } catch (err: any) {
      alert(err.message || "Could not update profile.");
    } finally {
      setUpdating(false);
    }
  };

  const getInitials = (name?: string) => {
    if (!name) return "PT";
    const parts = name.trim().split(" ");
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };

  const formatReportType = (category: string) => {
    switch (category) {
      case "blood_test":
        return "Lab Report";
      case "xray":
      case "ct_scan":
      case "mri":
        return "Radiology";
      case "prescription":
        return "Prescription";
      case "discharge_summary":
        return "Discharge";
      default:
        return "Clinical Report";
    }
  };

  const getCategoryColor = (category: string) => {
    switch (category) {
      case "blood_test":
        return {
          iconBg: "bg-rose-50 text-rose-500",
          badge: "bg-blue-50 text-blue-600 border-blue-100",
        };
      case "xray":
        return {
          iconBg: "bg-emerald-50 text-emerald-500",
          badge: "bg-indigo-50 text-indigo-600 border-indigo-100",
        };
      case "ct_scan":
      case "mri":
        return {
          iconBg: "bg-purple-50 text-purple-500",
          badge: "bg-purple-50 text-purple-600 border-purple-100",
        };
      case "prescription":
        return {
          iconBg: "bg-amber-50 text-amber-500",
          badge: "bg-amber-50 text-amber-600 border-amber-100",
        };
      default:
        return {
          iconBg: "bg-slate-50 text-slate-500",
          badge: "bg-slate-50 text-slate-600 border-slate-200",
        };
    }
  };

  return (
    <div className="space-y-6 sm:space-y-8 animate-in fade-in duration-300">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Patient Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage your health records, securely and easily.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            onClick={fetchData}
            className="p-2 text-slate-500 hover:text-blue-600 rounded-xl hover:bg-white border border-transparent hover:border-slate-200 transition shadow-none hover:shadow-sm"
            title="Refresh dashboard"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-16 text-center space-y-3 shadow-sm">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
          <p className="text-sm text-slate-600 font-medium">Loading your medical dashboard...</p>
        </div>
      ) : errorMsg ? (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-amber-900 space-y-3">
          <div className="flex items-center gap-2 font-semibold">
            <AlertCircle className="w-5 h-5 text-amber-600" /> Session Notice
          </div>
          <p className="text-sm text-amber-800">{errorMsg}</p>
          <div className="pt-2 flex gap-3">
            <Link
              href="/patient/login"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition"
            >
              Sign In Again
            </Link>
          </div>
        </div>
      ) : profile ? (
        <>
          {/* Top Hero Section: Patient Identity & Assurance Cards */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
            {/* Left Card: Patient Identity & Demographics (approx 65% width on desktop) */}
            <div className="lg:col-span-8 bg-gradient-to-r from-[#1E60E8] to-[#1B4FD8] rounded-2xl p-6 sm:p-7 text-white shadow-sm flex flex-col justify-between relative overflow-hidden">
              {/* Subtle radial background decorative element */}
              <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 rounded-full bg-white/5 pointer-events-none blur-2xl" />

              <div>
                {/* Top Row: Patient Info & Security Assurance Badge */}
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-center gap-3.5">
                    {/* Initials Avatar */}
                    <div className="w-14 h-14 rounded-full bg-white text-blue-700 font-extrabold text-lg flex items-center justify-center shadow-md flex-shrink-0">
                      {getInitials(profile.full_name)}
                    </div>
                    <div>
                      <span className="text-[11px] uppercase tracking-wider text-blue-200 font-bold block">
                        PATIENT
                      </span>
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <h2 className="text-xl sm:text-2xl font-bold tracking-tight">
                          {profile.full_name}
                        </h2>
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-200 border border-emerald-400/30 text-xs font-medium backdrop-blur-sm">
                          <Check className="w-3 h-3 text-emerald-300 stroke-[3]" />
                          <span>Verified Patient</span>
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-1 text-xs text-blue-100 font-mono">
                        <span>Patient ID: {profile.patient_id}</span>
                        <button
                          onClick={() => handleCopyId(profile.patient_id)}
                          className="p-1 hover:bg-white/20 rounded transition text-blue-100 hover:text-white"
                          title="Copy Patient ID"
                        >
                          {copied ? (
                            <Check className="w-3.5 h-3.5 text-emerald-300" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Top Right Security Assurance Badge */}
                  <div className="hidden sm:inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/10 backdrop-blur-md border border-white/20 text-xs text-blue-50">
                    <div className="w-4 h-4 rounded-full bg-emerald-400/20 text-emerald-300 flex items-center justify-center">
                      <Check className="w-3 h-3 stroke-[3]" />
                    </div>
                    <div className="text-right leading-tight">
                      <span className="block text-[10px] text-blue-200">Your records are</span>
                      <span className="font-semibold text-[11px]">Secure & Private</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Bottom Row: Demographic Details Grid */}
              <div className="mt-8 pt-5 border-t border-white/15 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                <div>
                  <div className="flex items-center gap-1.5 text-blue-200 mb-1">
                    <Calendar className="w-3.5 h-3.5" />
                    <span>Date of Birth</span>
                  </div>
                  <span className="font-semibold text-sm tracking-wide">
                    {formatDateOnly(profile.date_of_birth)}
                  </span>
                </div>

                <div>
                  <div className="flex items-center gap-1.5 text-blue-200 mb-1">
                    <User className="w-3.5 h-3.5" />
                    <span>Gender</span>
                  </div>
                  <span className="font-semibold text-sm capitalize">
                    {profile.gender || "Not specified"}
                  </span>
                </div>

                <div>
                  <div className="flex items-center gap-1.5 text-blue-200 mb-1">
                    <MapPin className="w-3.5 h-3.5" />
                    <span>Location</span>
                  </div>
                  <span className="font-semibold text-sm">Bengaluru, KA</span>
                </div>

                <div>
                  <div className="flex items-center gap-1.5 text-blue-200 mb-1">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Blood Group</span>
                  </div>
                  <span className="font-semibold text-sm font-mono text-emerald-200">
                    {profile.blood_group || "B+"}
                  </span>
                </div>
              </div>
            </div>

            {/* Right Card: Assurance Card with Medical Visual (approx 35% width on desktop) */}
            <div className="lg:col-span-4 bg-gradient-to-br from-blue-50/80 via-indigo-50/50 to-white rounded-2xl p-6 sm:p-7 border border-blue-100/80 shadow-sm flex flex-col justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900 leading-snug">
                  Your Health Records
                  <span className="block text-blue-600">In Your Control</span>
                </h3>
                <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                  Upload, access and share your medical reports anytime, anywhere with complete confidentiality.
                </p>
              </div>

              {/* 3D Style Healthcare Iconography Mockup */}
              <div className="mt-6 flex items-center justify-center py-2 relative">
                <div className="w-24 h-24 rounded-2xl bg-gradient-to-tr from-blue-500 to-indigo-600 shadow-lg shadow-blue-500/25 flex items-center justify-center relative">
                  <Activity className="w-12 h-12 text-white stroke-[2.5]" />
                  <div className="absolute -top-2 -right-2 w-7 h-7 rounded-full bg-emerald-500 text-white flex items-center justify-center shadow-md border-2 border-white">
                    <Check className="w-4 h-4 stroke-[3]" />
                  </div>
                  <div className="absolute -bottom-2 -left-2 w-7 h-7 rounded-full bg-slate-900 text-white flex items-center justify-center shadow-md border-2 border-white">
                    <Lock className="w-3.5 h-3.5" />
                  </div>
                </div>
              </div>

              <div className="text-[11px] text-center text-slate-400 font-medium">
                Encrypted with 256-bit Row Level Security
              </div>
            </div>
          </div>

          {/* Middle Section: 3 Quick Action Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {/* 1. Upload Report */}
            <Link
              href="/patient/upload"
              className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-[0_2px_8px_rgba(0,0,0,0.02)] hover:shadow-md hover:border-blue-300 transition group flex items-center justify-between"
            >
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center group-hover:scale-105 transition flex-shrink-0">
                  <UploadCloud className="w-6 h-6 stroke-[2]" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-900 text-sm group-hover:text-blue-600 transition">
                    Upload Report
                  </h4>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Add your medical reports in seconds
                  </p>
                </div>
              </div>
              <div className="w-8 h-8 rounded-full bg-slate-50 text-slate-400 group-hover:bg-blue-50 group-hover:text-blue-600 flex items-center justify-center transition flex-shrink-0">
                <ArrowRight className="w-4 h-4" />
              </div>
            </Link>

            {/* 2. Create Share QR */}
            <Link
              href="/patient/share"
              className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-[0_2px_8px_rgba(0,0,0,0.02)] hover:shadow-md hover:border-emerald-300 transition group flex items-center justify-between"
            >
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center group-hover:scale-105 transition flex-shrink-0">
                  <QrCode className="w-6 h-6 stroke-[2]" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-900 text-sm group-hover:text-emerald-600 transition">
                    Create Share QR
                  </h4>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Generate a secure QR code to share your records
                  </p>
                </div>
              </div>
              <div className="w-8 h-8 rounded-full bg-slate-50 text-slate-400 group-hover:bg-emerald-50 group-hover:text-emerald-600 flex items-center justify-center transition flex-shrink-0">
                <ArrowRight className="w-4 h-4" />
              </div>
            </Link>

            {/* 3. Medical Library */}
            <Link
              href="/patient/reports"
              className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-[0_2px_8px_rgba(0,0,0,0.02)] hover:shadow-md hover:border-purple-300 transition group flex items-center justify-between"
            >
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center group-hover:scale-105 transition flex-shrink-0">
                  <BookOpen className="w-6 h-6 stroke-[2]" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-900 text-sm group-hover:text-purple-600 transition">
                    Medical Library
                  </h4>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Browse and understand your medical reports
                  </p>
                </div>
              </div>
              <div className="w-8 h-8 rounded-full bg-slate-50 text-slate-400 group-hover:bg-purple-50 group-hover:text-purple-600 flex items-center justify-center transition flex-shrink-0">
                <ArrowRight className="w-4 h-4" />
              </div>
            </Link>
          </div>

          {/* Bottom Section: Recent Reports & Account Details (60% / 40%) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left: Recent Reports Table Card (approx 60% on desktop) */}
            <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3.5">
                <div className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-blue-600" />
                  <h3 className="font-bold text-slate-900 text-base">Recent Reports</h3>
                </div>
                <Link
                  href="/patient/reports"
                  className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1 transition"
                >
                  View All <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>

              {recentReports.length === 0 ? (
                <div className="text-center py-10 space-y-2">
                  <FileText className="w-8 h-8 text-slate-300 mx-auto" />
                  <p className="text-xs text-slate-500">No medical reports recorded yet.</p>
                  <Link
                    href="/patient/upload"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 text-blue-600 text-xs font-semibold hover:bg-blue-100 transition"
                  >
                    <UploadCloud className="w-3.5 h-3.5" /> Upload Your First Report
                  </Link>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-slate-400 text-[11px] font-semibold border-b border-slate-100">
                        <th className="pb-2.5 font-medium">REPORT NAME</th>
                        <th className="pb-2.5 font-medium">DATE UPLOADED</th>
                        <th className="pb-2.5 font-medium">REPORT TYPE</th>
                        <th className="pb-2.5 font-medium text-right">ACTIONS</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {recentReports.map((report) => {
                        const style = getCategoryColor(report.category);
                        return (
                          <tr key={report.id} className="hover:bg-slate-50/70 transition group">
                            <td className="py-3 font-semibold text-slate-900">
                              <div className="flex items-center gap-2.5">
                                <div
                                  className={`w-7 h-7 rounded-lg ${style.iconBg} flex items-center justify-center flex-shrink-0`}
                                >
                                  <FileText className="w-3.5 h-3.5" />
                                </div>
                                <span className="truncate max-w-[160px] sm:max-w-[200px]">
                                  {report.title}
                                </span>
                              </div>
                            </td>
                            <td className="py-3 text-slate-500 font-mono text-[11px]">
                              {report.report_date}
                            </td>
                            <td className="py-3">
                              <span
                                className={`px-2 py-0.5 rounded-full border text-[10px] font-medium ${style.badge}`}
                              >
                                {formatReportType(report.category)}
                              </span>
                            </td>
                            <td className="py-3 text-right">
                              <button
                                onClick={() => handleDownload(report)}
                                disabled={downloadingId === report.id}
                                className="text-blue-600 hover:text-blue-700 font-semibold text-xs px-2.5 py-1 rounded-md hover:bg-blue-50 transition"
                              >
                                {downloadingId === report.id ? "Loading..." : "View"}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Right: Account Details Card (approx 40% on desktop) */}
            <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3.5">
                <div className="flex items-center gap-2">
                  <User className="w-5 h-5 text-blue-600" />
                  <h3 className="font-bold text-slate-900 text-base">Account Details</h3>
                </div>
                <button
                  onClick={() => setShowEditModal(true)}
                  className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1 hover:underline"
                >
                  <Edit2 className="w-3.5 h-3.5" /> Edit
                </button>
              </div>

              <div className="space-y-3.5 text-xs">
                {/* Email Address */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-slate-500">
                    <Mail className="w-3.5 h-3.5 text-slate-400" />
                    <span>Email Address</span>
                  </div>
                  <span className="font-semibold text-slate-900 font-mono truncate max-w-[160px]">
                    {profile.email ? (
                      profile.email
                    ) : (
                      <span className="text-slate-400 italic font-sans font-normal">Not provided</span>
                    )}
                  </span>
                </div>

                {/* Phone Number */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-slate-500">
                    <Phone className="w-3.5 h-3.5 text-slate-400" />
                    <span>Phone Number</span>
                  </div>
                  <span className="font-semibold text-slate-900 font-mono">
                    {profile.phone_masked || "+91 ••••• •••••"}
                  </span>
                </div>

                {/* Address */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-slate-500">
                    <MapPin className="w-3.5 h-3.5 text-slate-400" />
                    <span>Address</span>
                  </div>
                  <span className="font-semibold text-slate-900 truncate max-w-[160px]">
                    Bengaluru, Karnataka, India
                  </span>
                </div>

                {/* Account Status */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-slate-500">
                    <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
                    <span>Account Status</span>
                  </div>
                  <span className="font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100">
                    Active
                  </span>
                </div>

                {/* Member Since */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-slate-500">
                    <Calendar className="w-3.5 h-3.5 text-slate-400" />
                    <span>Member Since</span>
                  </div>
                  <span className="font-semibold text-slate-900 font-mono">
                    {new Date(profile.created_at).toLocaleDateString("en-GB", {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </>
      ) : null}

      {/* Edit Clinical Info Modal */}
      {showEditModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4 border border-slate-200">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-slate-900">Edit Clinical Details</h3>
              <button
                onClick={() => setShowEditModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-semibold"
              >
                ✕
              </button>
            </div>
            <form onSubmit={handleSaveUpdates} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                  Date of Birth
                </label>
                <input
                  type="date"
                  value={editDob}
                  onChange={(e) => setEditDob(e.target.value)}
                  max={new Date().toISOString().split("T")[0]}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                  Blood Group
                </label>
                <select
                  value={bloodGroup}
                  onChange={(e) => setBloodGroup(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                  className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updating}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition disabled:opacity-60"
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
