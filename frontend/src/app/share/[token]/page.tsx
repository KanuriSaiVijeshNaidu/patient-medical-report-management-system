"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  Clock,
  FileText,
  Download,
  AlertTriangle,
  Loader2,
  Calendar,
  ShieldAlert,
  ArrowLeft,
  Lock,
  ExternalLink,
  Files,
  CheckCircle2,
  ImageIcon,
} from "lucide-react";
import { viewSharedReport, SharedReportViewResponse, SharedReportItem } from "@/lib/api";
import { formatDateOnly } from "@/lib/utils";

const CATEGORY_LABELS: Record<string, string> = {
  blood_test: "Blood Test",
  xray: "X-Ray",
  ct_scan: "CT Scan",
  mri: "MRI Scan",
  prescription: "Prescription",
  discharge_summary: "Discharge Summary",
  other: "Other",
};

export default function SharedReportViewerPage({
  params,
}: {
  params: { token: string };
}) {
  const token = params?.token;

  const [loading, setLoading] = useState(true);
  const [reportData, setReportData] = useState<SharedReportViewResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isRateLimited, setIsRateLimited] = useState(false);
  const [activeReportIndex, setActiveReportIndex] = useState(0);

  useEffect(() => {
    if (!token) {
      setErrorMsg("Invalid or missing share token.");
      setLoading(false);
      return;
    }

    const validateToken = async () => {
      setLoading(true);
      setErrorMsg(null);
      setIsRateLimited(false);
      try {
        const data = await viewSharedReport(token);
        setReportData(data);
      } catch (err: any) {
        const msg = err.message || "Failed to access shared report.";
        if (
          msg.includes("429") ||
          msg.toLowerCase().includes("too many requests") ||
          msg.toLowerCase().includes("rate limit")
        ) {
          setIsRateLimited(true);
        }
        setErrorMsg(msg);
      } finally {
        setLoading(false);
      }
    };

    validateToken();
  }, [token]);

  const formatFileSize = (bytes: number) => {
    if (!bytes) return "0 KB";
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getCategoryLabel = (cat: string) => {
    return CATEGORY_LABELS[cat] || cat.replace("_", " ");
  };

  const handleOpenPdf = (url?: string) => {
    const targetUrl = url || currentReport?.download_url || reportData?.download_url;
    if (targetUrl) {
      window.open(targetUrl, "_blank", "noopener,noreferrer");
    }
  };

  // Derive reports list
  const reportsList: SharedReportItem[] =
    reportData?.reports && reportData.reports.length > 0
      ? reportData.reports
      : reportData
      ? [
          {
            report_id: reportData.report_id,
            title: reportData.title,
            category: reportData.category,
            report_date: reportData.report_date,
            file_size_bytes: reportData.file_size_bytes,
            mime_type: reportData.mime_type,
            verification_status: reportData.verification_status,
            download_url: reportData.download_url,
            download_url_expires_in_seconds: reportData.download_url_expires_in_seconds,
          },
        ]
      : [];

  const currentReport = reportsList[activeReportIndex] || reportsList[0];

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Navigation Bar */}
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Healthcare Portal Home
          </Link>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-semibold border border-blue-200">
            <Lock className="w-3.5 h-3.5" /> End-to-End Private Access
          </div>
        </div>

        {/* Loading State */}
        {loading ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-4 shadow-sm">
            <Loader2 className="w-10 h-10 text-blue-600 animate-spin mx-auto" />
            <div className="space-y-1">
              <h2 className="text-base font-bold text-slate-900">Validating Cryptographic Share Token</h2>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Verifying token signature, authorization scope, and expiration status against the secure registry...
              </p>
            </div>
          </div>
        ) : errorMsg || !reportData ? (
          /* Invalid / Expired / Revoked / Rate-Limited State */
          <div className="bg-white rounded-2xl border border-slate-200 p-8 sm:p-10 text-center space-y-5 shadow-sm">
            <div className="w-14 h-14 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
              <AlertTriangle className="w-7 h-7" />
            </div>

            <div className="space-y-2">
              <h2 className="text-xl font-bold text-slate-900">
                {isRateLimited ? "Too Many Access Attempts" : "Shared Medical Report Unavailable"}
              </h2>
              <p className="text-xs text-slate-600 max-w-md mx-auto leading-relaxed">
                {isRateLimited
                  ? "Too many lookup attempts have been received from your network. Please wait a moment before trying again."
                  : "This share grant is either invalid, has expired, or was revoked by the patient. Temporary links are strictly time-limited and cannot be accessed once expired."}
              </p>
            </div>

            <div className="pt-2 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link
                href="/"
                className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition"
              >
                Return to Portal Home
              </Link>
            </div>
          </div>
        ) : (
          /* Valid Authorized Share State */
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            {/* Header Banner */}
            <div className="bg-gradient-to-r from-blue-700 via-blue-600 to-indigo-700 p-6 sm:p-8 text-white space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/20 text-xs font-semibold backdrop-blur-sm">
                  <ShieldCheck className="w-4 h-4 text-emerald-300" />
                  <span>Patient Authorized Share Session</span>
                </div>
                <div className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-200 text-xs font-semibold border border-emerald-400/30">
                  <Files className="w-3.5 h-3.5" />
                  <span>
                    {reportsList.length} {reportsList.length === 1 ? "Report" : "Reports"} Available
                  </span>
                </div>
              </div>

              {reportsList.length === 1 ? (
                <>
                  <h1 className="text-2xl sm:text-3xl font-extrabold">{currentReport?.title}</h1>
                  <div className="flex flex-wrap items-center gap-4 text-xs text-blue-100">
                    <span className="font-mono bg-white/10 px-2 py-0.5 rounded">
                      {currentReport?.report_id}
                    </span>
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5" /> Report Date: {formatDateOnly(currentReport?.report_date)}
                    </span>
                    <span>Size: {formatFileSize(currentReport?.file_size_bytes || 0)}</span>
                  </div>
                </>
              ) : (
                <>
                  <h1 className="text-2xl sm:text-3xl font-extrabold">Shared Medical Reports</h1>
                  <p className="text-xs text-blue-100">
                    The patient has granted you temporary access to review {reportsList.length} diagnostic records.
                    Select and view each report below.
                  </p>
                </>
              )}
            </div>

            {/* Content Body */}
            <div className="p-6 sm:p-8 space-y-6">
              {/* Access Notice and Timer */}
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3 text-xs text-amber-900">
                <Clock className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="font-semibold">Time-Limited Access Authorized</p>
                  <p className="text-amber-800 leading-relaxed">
                    This share session is valid for temporary clinical review and will expire at{" "}
                    <strong>{new Date(reportData.share_expires_at).toLocaleTimeString()}</strong>.
                  </p>
                </div>
              </div>

              {/* Multiple Reports List (If 2+ reports in session) */}
              {reportsList.length > 1 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-bold text-slate-900">
                      Authorized Medical Reports ({reportsList.length})
                    </h2>
                    <span className="text-xs text-slate-500">Click any report to view or download</span>
                  </div>

                  <div className="grid gap-3">
                    {reportsList.map((rep, idx) => {
                      const isSelected = idx === activeReportIndex;
                      const isRepImage = rep.mime_type?.startsWith("image/");
                      return (
                        <div
                          key={rep.report_id}
                          onClick={() => setActiveReportIndex(idx)}
                          className={`rounded-xl border p-4 transition cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                            isSelected
                              ? "bg-blue-50/50 border-blue-400 ring-1 ring-blue-400/40"
                              : "bg-white border-slate-200 hover:border-slate-300"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                              {isRepImage ? <ImageIcon className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                            </div>
                            <div className="space-y-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="font-bold text-slate-900 text-sm">{rep.title}</h3>
                                <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-semibold">
                                  {rep.report_id}
                                </span>
                              </div>
                              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                                <span className="font-medium text-slate-700">
                                  {getCategoryLabel(rep.category)}
                                </span>
                                <span className="flex items-center gap-1">
                                  <Calendar className="w-3 h-3" /> {formatDateOnly(rep.report_date)}
                                </span>
                                <span>{formatFileSize(rep.file_size_bytes)}</span>
                                {rep.verification_status === "hospital_verified" ? (
                                  <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700 font-semibold">
                                    <ShieldCheck className="w-3 h-3 text-emerald-600" /> Verified
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-[10px] text-slate-500">
                                    <ShieldAlert className="w-3 h-3 text-slate-400" /> Patient Upload
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-2 justify-end pt-2 sm:pt-0">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenPdf(rep.download_url);
                              }}
                              className="px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-sm"
                            >
                              <Download className="w-3.5 h-3.5" /> {isRepImage ? "View / Download Image" : "View / Download PDF"}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Selected / Current Report Metadata Details */}
              <div className="space-y-3 pt-2">
                {reportsList.length > 1 && (
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Selected Report Details: {currentReport?.title}
                  </h3>
                )}
                <div className="grid sm:grid-cols-2 gap-4 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs">
                  <div>
                    <span className="text-slate-500 block">Report ID</span>
                    <span className="font-mono font-semibold text-slate-800">
                      {currentReport?.report_id}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Category</span>
                    <span className="font-semibold text-slate-800 capitalize">
                      {getCategoryLabel(currentReport?.category || "other")}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Report Date</span>
                    <span className="font-semibold text-slate-800">
                      {formatDateOnly(currentReport?.report_date)}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">File Format</span>
                    <span className="font-semibold text-slate-800">
                      {currentReport?.mime_type?.startsWith("image/")
                        ? `Medical Photo / Scan (${currentReport?.mime_type})`
                        : `PDF Document (${currentReport?.mime_type || "application/pdf"})`}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Verification Status</span>
                    <span className="font-semibold text-slate-800">
                      {currentReport?.verification_status === "hospital_verified" ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700">
                          <ShieldCheck className="w-3.5 h-3.5" /> Hospital Verified
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-slate-600">
                          <ShieldAlert className="w-3.5 h-3.5" /> Patient Self-Uploaded
                        </span>
                      )}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Authorized Scope</span>
                    <span className="font-semibold text-slate-800">
                      {reportsList.length === 1
                        ? "Single Specific Diagnostic Record"
                        : `Bundle of ${reportsList.length} Selected Patient Records`}
                    </span>
                  </div>
                </div>
              </div>

              {/* Inline Preview for Photos / Scans */}
              {currentReport?.mime_type?.startsWith("image/") && currentReport?.download_url && (
                <div className="rounded-xl border border-slate-200 overflow-hidden bg-slate-50 p-3 sm:p-4 text-center space-y-2">
                  <div className="text-[11px] font-semibold text-slate-600 flex items-center justify-center gap-1.5">
                    <ImageIcon className="w-4 h-4 text-blue-600" />
                    <span>Authorized Medical Image Preview</span>
                  </div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={currentReport.download_url}
                    alt={currentReport.title}
                    className="max-h-[480px] w-auto mx-auto rounded-lg object-contain shadow-sm border border-slate-200 bg-white"
                  />
                </div>
              )}

              {/* View / Download Primary Action */}
              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={() => handleOpenPdf(currentReport?.download_url)}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm transition shadow-md hover:shadow-lg"
                >
                  <Download className="w-4 h-4" />{" "}
                  {currentReport?.mime_type?.startsWith("image/")
                    ? "Open Full-Resolution Image"
                    : "Open Selected Document"}{" "}
                  ({currentReport?.title})
                </button>
                <p className="text-[11px] text-slate-400 mt-2">
                  Opens a fresh, secure temporary view stream in a separate tab.
                </p>
              </div>

              {/* Clinical Privacy Notice */}
              <div className="pt-4 border-t border-slate-100 text-[11px] text-slate-400 text-center leading-relaxed">
                Confidentiality Notice: These medical records are legally privileged and strictly confidential.
                Unintended recipients are prohibited from downloading, disseminating, or storing these records.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
