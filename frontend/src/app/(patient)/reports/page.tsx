"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import {
  FileText,
  Upload,
  Download,
  Trash2,
  Filter,
  Search,
  Calendar,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  AlertCircle,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
  X,
  FileCheck,
  QrCode,
  Copy,
  Check,
  Clock,
  AlertTriangle,
  Ban,
  Layers,
} from "lucide-react";
import {
  getMyReports,
  getReportDownloadUrl,
  deleteMedicalReport,
  createReportShare,
  revokeReportShare,
  MedicalReport,
  ShareGrantResponse,
} from "@/lib/api";

const CATEGORIES = [
  { value: "all", label: "All Records" },
  { value: "blood_test", label: "Blood Tests" },
  { value: "xray", label: "X-Rays" },
  { value: "ct_scan", label: "CT Scans" },
  { value: "mri", label: "MRI Scans" },
  { value: "prescription", label: "Prescriptions" },
  { value: "discharge_summary", label: "Discharge Summaries" },
  { value: "other", label: "Other" },
];

const DURATION_OPTIONS = [
  { label: "15 Minutes (Recommended)", seconds: 900 },
  { label: "1 Hour", seconds: 3600 },
  { label: "24 Hours", seconds: 86400 },
];

export default function ReportsLibraryPage() {
  const router = useRouter();
  const [reports, setReports] = useState<MedicalReport[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  // Download state tracking by report ID
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // Multi-select state
  const [selectedReportIds, setSelectedReportIds] = useState<string[]>([]);

  // Deletion modal state
  const [reportToDelete, setReportToDelete] = useState<MedicalReport | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Share Modal State (supports 1 or multiple reports)
  const [reportsToShare, setReportsToShare] = useState<MedicalReport[]>([]);
  const [shareDuration, setShareDuration] = useState<number>(900);
  const [sharing, setSharing] = useState(false);
  const [activeShare, setActiveShare] = useState<ShareGrantResponse | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);

  const fetchReports = async (cat?: string) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await getMyReports(cat === "all" ? undefined : cat);
      setReports(data || []);
    } catch (err: any) {
      if (
        err.message?.includes("Authentication required") ||
        err.message?.includes("401") ||
        err.message?.includes("sign in")
      ) {
        setReports([]);
        router.push("/patient/login");
        return;
      }
      setErrorMsg(err.message || "Failed to load medical reports.");
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
    fetchReports(selectedCategory);
  }, [selectedCategory]);

  const filteredReports = reports.filter((r) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      r.title.toLowerCase().includes(q) ||
      r.report_id.toLowerCase().includes(q) ||
      r.category.toLowerCase().includes(q)
    );
  });

  const formatFileSize = (bytes: number) => {
    if (!bytes) return "0 KB";
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getCategoryLabel = (cat: string) => {
    const found = CATEGORIES.find((c) => c.value === cat);
    return found ? found.label : cat.replace("_", " ");
  };

  const toggleSelectReport = (reportId: string) => {
    setSelectedReportIds((prev) =>
      prev.includes(reportId)
        ? prev.filter((id) => id !== reportId)
        : [...prev, reportId]
    );
  };

  const handleSelectAll = () => {
    const visibleIds = filteredReports.map((r) => r.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedReportIds.includes(id));
    if (allSelected) {
      setSelectedReportIds((prev) => prev.filter((id) => !visibleIds.includes(id)));
    } else {
      setSelectedReportIds((prev) => Array.from(new Set([...prev, ...visibleIds])));
    }
  };

  const handleDownload = async (report: MedicalReport) => {
    setDownloadingId(report.id);
    setActionNotice(null);
    try {
      const result = await getReportDownloadUrl(report.report_id || report.id);
      if (result.download_url) {
        window.open(result.download_url, "_blank", "noopener,noreferrer");
        setActionNotice(`Secure view link generated for ${report.title}. Expires in 5 minutes.`);
      }
    } catch (err: any) {
      alert(`Could not generate download URL: ${err.message}`);
    } finally {
      setDownloadingId(null);
    }
  };

  const confirmDelete = async () => {
    if (!reportToDelete) return;
    setDeleting(true);
    try {
      await deleteMedicalReport(reportToDelete.id);
      setReports((prev) => prev.filter((r) => r.id !== reportToDelete.id));
      setSelectedReportIds((prev) => prev.filter((id) => id !== reportToDelete.id));
      setActionNotice(`Report "${reportToDelete.title}" was deleted permanently.`);
      setReportToDelete(null);
    } catch (err: any) {
      alert(`Failed to delete report: ${err.message}`);
    } finally {
      setDeleting(false);
    }
  };

  const openShareModal = (report: MedicalReport) => {
    // If multiple reports are already selected and include this report, share the bundle
    if (selectedReportIds.includes(report.id) && selectedReportIds.length > 1) {
      const selected = reports.filter((r) => selectedReportIds.includes(r.id));
      setReportsToShare(selected);
    } else {
      setReportsToShare([report]);
    }
    setActiveShare(null);
    setQrDataUrl(null);
    setShareError(null);
    setCopied(false);
    setShareDuration(900);
  };

  const openShareModalForSelected = () => {
    const selected = reports.filter((r) => selectedReportIds.includes(r.id));
    if (selected.length === 0) return;
    setReportsToShare(selected);
    setActiveShare(null);
    setQrDataUrl(null);
    setShareError(null);
    setCopied(false);
    setShareDuration(900);
  };

  const removeReportFromShare = (reportId: string) => {
    if (reportsToShare.length <= 1) return;
    setReportsToShare((prev) => prev.filter((r) => r.id !== reportId));
  };

  const handleGenerateShare = async () => {
    if (reportsToShare.length === 0) return;
    setSharing(true);
    setShareError(null);
    try {
      const targetIds = reportsToShare.map((r) => r.id);
      const share = await createReportShare(targetIds, shareDuration);
      setActiveShare(share);

      // Generate QR Code data URL
      const qrUrl = await QRCode.toDataURL(share.share_url, {
        width: 280,
        margin: 2,
        color: {
          dark: "#0f172a",
          light: "#ffffff",
        },
      });
      setQrDataUrl(qrUrl);
    } catch (err: any) {
      setShareError(err.message || "Failed to generate share link.");
    } finally {
      setSharing(false);
    }
  };

  const handleCopyLink = () => {
    if (!activeShare) return;
    navigator.clipboard.writeText(activeShare.share_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRevokeShare = async () => {
    if (!activeShare) return;
    setRevoking(true);
    try {
      await revokeReportShare(activeShare.grant_id);
      setActiveShare(null);
      setQrDataUrl(null);
      setActionNotice(`Share grant revoked successfully. Access terminated immediately.`);
      setReportsToShare([]);
    } catch (err: any) {
      setShareError(err.message || "Failed to revoke share.");
    } finally {
      setRevoking(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Medical Records Library</h1>
          <p className="text-xs text-slate-500">
            View, download, and securely share your laboratory tests, diagnostic scans, and clinical reports via expiring QR codes.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchReports(selectedCategory)}
            className="p-2 text-slate-600 hover:text-blue-600 rounded-lg hover:bg-slate-100 transition"
            title="Refresh reports"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <Link
            href="/upload"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition shadow-sm"
          >
            <Upload className="w-4 h-4" /> Upload New Report
          </Link>
        </div>
      </div>

      {/* Notifications */}
      {actionNotice && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3.5 flex items-center justify-between text-emerald-900 text-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>{actionNotice}</span>
          </div>
          <button onClick={() => setActionNotice(null)} className="text-emerald-500 hover:text-emerald-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {errorMsg && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start gap-3 text-rose-900 text-xs">
          <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold">Notice:</span> {errorMsg}
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-500 hover:text-rose-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Search & Category Filter Bar */}
      <div className="space-y-3">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search reports by title or ID (e.g. REP-2026-XXXXXX)..."
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition bg-white"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.value}
              onClick={() => setSelectedCategory(cat.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition ${
                selectedCategory === cat.value
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content Area */}
      {loading ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-3">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
          <p className="text-sm text-slate-600">Retrieving encrypted medical records...</p>
        </div>
      ) : filteredReports.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <FileText className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-base">No medical reports found</h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
              {searchQuery
                ? "No records matched your search query. Try searching for a different keyword or category."
                : "You have not uploaded any medical records in this category yet."}
            </p>
          </div>
          <Link
            href="/upload"
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold transition"
          >
            <Upload className="w-4 h-4" /> Upload Your First Report
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Multi-Selection Control Bar */}
          <div className="bg-white rounded-xl border border-slate-200 p-3 sm:p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <label className="inline-flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700 select-none">
                <input
                  type="checkbox"
                  checked={
                    filteredReports.length > 0 &&
                    filteredReports.every((r) => selectedReportIds.includes(r.id))
                  }
                  onChange={handleSelectAll}
                  className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-slate-300 cursor-pointer"
                />
                <span>Select All Visible ({filteredReports.length})</span>
              </label>

              {selectedReportIds.length > 0 && (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 font-semibold border border-blue-200">
                  {selectedReportIds.length} selected
                </span>
              )}
            </div>

            {selectedReportIds.length > 0 && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={openShareModalForSelected}
                  className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-sm"
                >
                  <QrCode className="w-3.5 h-3.5" /> Share Selected ({selectedReportIds.length})
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedReportIds([])}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-medium transition"
                >
                  Clear Selection
                </button>
              </div>
            )}
          </div>

          {/* Reports Grid / List */}
          <div className="grid gap-4">
            {filteredReports.map((report) => {
              const isSelected = selectedReportIds.includes(report.id);
              return (
                <div
                  key={report.id}
                  className={`rounded-xl border p-5 shadow-sm transition flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                    isSelected
                      ? "bg-blue-50/30 border-blue-400 ring-1 ring-blue-400/40"
                      : "bg-white border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-start gap-3.5">
                    {/* Selection Checkbox */}
                    <div className="pt-2">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelectReport(report.id)}
                        aria-label={`Select report ${report.title}`}
                        className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-slate-300 cursor-pointer"
                      />
                    </div>

                    <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <FileText className="w-5 h-5" />
                    </div>

                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-bold text-slate-900 text-sm sm:text-base">
                          {report.title}
                        </h3>
                        <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-semibold">
                          {report.report_id}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                        <span className="inline-flex items-center gap-1 text-slate-700 font-medium">
                          <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
                          {getCategoryLabel(report.category)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3.5 h-3.5" /> Date: {report.report_date}
                        </span>
                        <span>{formatFileSize(report.file_size_bytes)}</span>
                      </div>

                      {/* Verification Status Pill */}
                      <div className="pt-1">
                        {report.verification_status === "hospital_verified" ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <ShieldCheck className="w-3 h-3 text-emerald-600" /> Hospital Verified
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                            <ShieldAlert className="w-3 h-3 text-slate-400" /> Patient Self-Uploaded
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center gap-2 pt-3 sm:pt-0 border-t sm:border-t-0 border-slate-100 justify-end">
                    {/* Share QR Button */}
                    <button
                      onClick={() => openShareModal(report)}
                      className="px-3.5 py-2 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-xs font-semibold flex items-center gap-1.5 transition border border-emerald-200"
                      title="Generate time-limited QR share"
                    >
                      <QrCode className="w-3.5 h-3.5" /> Share QR
                    </button>

                    {/* View / Download Button */}
                    <button
                      onClick={() => handleDownload(report)}
                      disabled={downloadingId === report.id}
                      className="px-3.5 py-2 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold flex items-center gap-1.5 transition border border-blue-200 disabled:opacity-60"
                      title="Generate secure short-lived view link"
                    >
                      {downloadingId === report.id ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Preparing...
                        </>
                      ) : (
                        <>
                          <Download className="w-3.5 h-3.5" /> View / Download
                        </>
                      )}
                    </button>

                    {/* Delete Button */}
                    <button
                      onClick={() => setReportToDelete(report)}
                      className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition border border-transparent hover:border-rose-200"
                      title="Delete report"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Share QR Modal (Supports Single & Multiple Reports) */}
      {reportsToShare.length > 0 && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 sm:p-8 shadow-xl space-y-5 border border-slate-200 max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-slate-100 pb-3">
              <div>
                <div className="inline-flex items-center gap-1.5 text-emerald-600 text-xs font-semibold mb-1">
                  <QrCode className="w-4 h-4" />
                  <span>
                    {reportsToShare.length === 1
                      ? "Secure Report Sharing"
                      : `Multi-Report QR Sharing (${reportsToShare.length} Records)`}
                  </span>
                </div>
                {reportsToShare.length === 1 ? (
                  <>
                    <h3 className="text-lg font-bold text-slate-900 truncate max-w-xs sm:max-w-md">
                      {reportsToShare[0].title}
                    </h3>
                    <span className="font-mono text-xs text-slate-500 font-semibold">
                      {reportsToShare[0].report_id}
                    </span>
                  </>
                ) : (
                  <>
                    <h3 className="text-lg font-bold text-slate-900">
                      Share {reportsToShare.length} Medical Reports with One QR
                    </h3>
                    <p className="text-xs text-slate-500">
                      Generate a single session link allowing the doctor to review all selected records.
                    </p>
                  </>
                )}
              </div>
              <button
                onClick={() => setReportsToShare([])}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Error in modal */}
            {shareError && (
              <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-xs text-rose-800 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">{shareError}</div>
              </div>
            )}

            {!activeShare ? (
              /* Share Configuration State */
              <div className="space-y-4">
                {/* List of included reports */}
                {reportsToShare.length > 1 && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                      <span>Included Records ({reportsToShare.length})</span>
                      <span className="text-[11px] text-slate-400">All accessible via this single QR</span>
                    </div>
                    <div className="max-h-36 overflow-y-auto space-y-1.5 p-2 bg-slate-50 rounded-xl border border-slate-200">
                      {reportsToShare.map((r) => (
                        <div
                          key={r.id}
                          className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-200 text-xs"
                        >
                          <div className="flex items-center gap-2 truncate">
                            <FileText className="w-3.5 h-3.5 text-blue-600 flex-shrink-0" />
                            <span className="font-semibold text-slate-900 truncate">{r.title}</span>
                            <span className="font-mono text-[10px] text-slate-500">{r.report_id}</span>
                          </div>
                          {reportsToShare.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeReportFromShare(r.id)}
                              className="text-slate-400 hover:text-rose-600 p-1 rounded"
                              title="Remove from this share QR"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                    Share Expiration Duration
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {DURATION_OPTIONS.map((opt) => (
                      <button
                        key={opt.seconds}
                        type="button"
                        onClick={() => setShareDuration(opt.seconds)}
                        className={`p-3 rounded-xl border text-xs font-medium text-center transition ${
                          shareDuration === opt.seconds
                            ? "border-emerald-500 bg-emerald-50 text-emerald-800 font-semibold ring-1 ring-emerald-500"
                            : "border-slate-200 hover:bg-slate-50 text-slate-700"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Bearer Credential Warning Banner */}
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-900 space-y-1.5">
                  <div className="flex items-center gap-2 font-semibold">
                    <AlertTriangle className="w-4 h-4 text-amber-600" /> Bearer Credential Notice
                  </div>
                  <p className="leading-relaxed">
                    {reportsToShare.length === 1
                      ? "This QR code generates an opaque, temporary access link. Anyone who scans this code can view this single report until it expires or is revoked."
                      : `This QR code generates an opaque, temporary access link allowing the recipient to view and download all ${reportsToShare.length} selected reports until the session expires or is revoked.`}
                  </p>
                </div>

                <div className="pt-2 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setReportsToShare([])}
                    className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleGenerateShare}
                    disabled={sharing}
                    className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold transition flex items-center gap-2 disabled:opacity-60 shadow-sm"
                  >
                    {sharing ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" /> Generating QR...
                      </>
                    ) : (
                      <>
                        <QrCode className="w-4 h-4" /> Generate Secure QR
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              /* Active Share Generated State */
              <div className="space-y-5 text-center">
                {/* QR Display */}
                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6 flex flex-col items-center justify-center space-y-3">
                  {qrDataUrl ? (
                    <img
                      src={qrDataUrl}
                      alt="Medical Report Share QR"
                      className="w-56 h-56 rounded-xl shadow-sm border border-slate-200 bg-white p-2"
                    />
                  ) : (
                    <div className="w-56 h-56 flex items-center justify-center">
                      <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                    </div>
                  )}

                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-semibold">
                    <Clock className="w-3.5 h-3.5" />
                    <span>
                      Expires: {new Date(activeShare.expires_at).toLocaleTimeString()} ({Math.round(activeShare.expires_in_seconds / 60)} min)
                    </span>
                  </div>

                  {/* Included reports count pill */}
                  <div className="text-xs text-slate-600">
                    <span className="font-semibold text-slate-800">
                      {activeShare.reports_count || reportsToShare.length}{" "}
                      {(activeShare.reports_count || reportsToShare.length) === 1 ? "Report" : "Reports"}
                    </span>{" "}
                    authorized in this QR session
                  </div>
                </div>

                {/* List of included reports */}
                {reportsToShare.length > 1 && (
                  <div className="text-left space-y-1.5 p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs">
                    <div className="font-semibold text-slate-700 mb-1">Reports in this QR bundle:</div>
                    <div className="max-h-28 overflow-y-auto space-y-1">
                      {reportsToShare.map((r) => (
                        <div key={r.id} className="flex items-center gap-2 text-slate-600 truncate">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                          <span className="truncate font-medium">{r.title}</span>
                          <span className="font-mono text-[10px] text-slate-400">({r.report_id})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Share Link Input with Copy Button */}
                <div className="space-y-1.5 text-left">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                    Opaque Share Link
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={activeShare.share_url}
                      className="flex-1 px-3 py-2 text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg text-slate-700 truncate"
                    />
                    <button
                      type="button"
                      onClick={handleCopyLink}
                      className="px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition flex items-center gap-1.5 flex-shrink-0"
                    >
                      {copied ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-300" /> Copied!
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" /> Copy Link
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Warning Reminder */}
                <p className="text-[11px] text-slate-500 leading-relaxed text-left">
                  • The recipient page will validate this token and generate temporary download URLs for all authorized reports.<br />
                  • No patient name, Aadhaar, or unselected medical records are exposed.<br />
                  • You can terminate access immediately using the revoke button below.
                </p>

                {/* Actions: Done / Revoke */}
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={handleRevokeShare}
                    disabled={revoking}
                    className="px-4 py-2 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-semibold transition flex items-center gap-1.5 disabled:opacity-60"
                  >
                    {revoking ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Revoking...
                      </>
                    ) : (
                      <>
                        <Ban className="w-3.5 h-3.5" /> Revoke Access Now
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => setReportsToShare([])}
                    className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition shadow-sm"
                  >
                    Done
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {reportToDelete && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4 border border-slate-200">
            <div className="w-10 h-10 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center">
              <Trash2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">Delete Medical Report?</h3>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                Are you sure you want to delete <span className="font-semibold text-slate-800">"{reportToDelete.title}"</span> ({reportToDelete.report_id})? This will permanently delete the document from private storage and cannot be undone.
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setReportToDelete(null)}
                className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={deleting}
                className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold transition disabled:opacity-60 flex items-center gap-1.5"
              >
                {deleting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Deleting...
                  </>
                ) : (
                  "Delete Report"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
