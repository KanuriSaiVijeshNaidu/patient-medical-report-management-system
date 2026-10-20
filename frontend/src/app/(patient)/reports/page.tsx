"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import {
  FileText,
  UploadCloud,
  Download,
  Trash2,
  Search,
  Calendar,
  ShieldCheck,
  Loader2,
  AlertCircle,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
  X,
  QrCode,
  Copy,
  Check,
  Clock,
  AlertTriangle,
  FlaskConical,
  Scan,
  Aperture,
  Brain,
  Pill,
  MoreHorizontal,
  ChevronDown,
  Layers,
  ArrowUpDown,
  Eye,
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

interface CategoryDef {
  value: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  colorClass: string;
  badgeClass: string;
  iconBgClass: string;
}

const CATEGORY_MAP: Record<string, CategoryDef> = {
  all: {
    value: "all",
    label: "All Reports",
    icon: Layers,
    colorClass: "text-blue-600",
    badgeClass: "bg-blue-50 text-blue-600 border-blue-200",
    iconBgClass: "bg-blue-50 text-blue-600",
  },
  blood_test: {
    value: "blood_test",
    label: "Blood Tests",
    icon: FlaskConical,
    colorClass: "text-rose-500",
    badgeClass: "bg-rose-50 text-rose-600 border-rose-200",
    iconBgClass: "bg-rose-50 text-rose-500",
  },
  xray: {
    value: "xray",
    label: "X-Rays",
    icon: Scan,
    colorClass: "text-blue-500",
    badgeClass: "bg-blue-50 text-blue-600 border-blue-200",
    iconBgClass: "bg-blue-50 text-blue-500",
  },
  ct_scan: {
    value: "ct_scan",
    label: "CT Scans",
    icon: Aperture,
    colorClass: "text-purple-500",
    badgeClass: "bg-purple-50 text-purple-600 border-purple-200",
    iconBgClass: "bg-purple-50 text-purple-500",
  },
  mri: {
    value: "mri",
    label: "MRI Scans",
    icon: Brain,
    colorClass: "text-emerald-500",
    badgeClass: "bg-emerald-50 text-emerald-600 border-emerald-200",
    iconBgClass: "bg-emerald-50 text-emerald-500",
  },
  prescription: {
    value: "prescription",
    label: "Prescriptions",
    icon: Pill,
    colorClass: "text-amber-500",
    badgeClass: "bg-amber-50 text-amber-600 border-amber-200",
    iconBgClass: "bg-amber-50 text-amber-500",
  },
  other: {
    value: "other",
    label: "Other",
    icon: MoreHorizontal,
    colorClass: "text-slate-500",
    badgeClass: "bg-slate-50 text-slate-600 border-slate-200",
    iconBgClass: "bg-slate-50 text-slate-500",
  },
};

const CATEGORIES_LIST = [
  CATEGORY_MAP.all,
  CATEGORY_MAP.blood_test,
  CATEGORY_MAP.xray,
  CATEGORY_MAP.ct_scan,
  CATEGORY_MAP.mri,
  CATEGORY_MAP.prescription,
  CATEGORY_MAP.other,
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
  const [sortBy, setSortBy] = useState<"newest" | "oldest" | "title">("newest");
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

  // Share Modal State
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

  // Filtering & Sorting
  const filteredReports = reports
    .filter((r) => {
      if (selectedCategory !== "all") {
        if (selectedCategory === "other") {
          const standardCats = ["blood_test", "xray", "ct_scan", "mri", "prescription"];
          if (standardCats.includes(r.category)) return false;
        } else if (r.category !== selectedCategory) {
          return false;
        }
      }

      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        r.title.toLowerCase().includes(q) ||
        r.report_id.toLowerCase().includes(q) ||
        r.category.toLowerCase().includes(q)
      );
    })
    .sort((a, b) => {
      if (sortBy === "newest") {
        return new Date(b.report_date).getTime() - new Date(a.report_date).getTime();
      }
      if (sortBy === "oldest") {
        return new Date(a.report_date).getTime() - new Date(b.report_date).getTime();
      }
      return a.title.localeCompare(b.title);
    });

  // Calculate counts for categories
  const getCategoryCount = (catValue: string) => {
    if (catValue === "all") return reports.length;
    if (catValue === "other") {
      const standardCats = ["blood_test", "xray", "ct_scan", "mri", "prescription"];
      return reports.filter((r) => !standardCats.includes(r.category)).length;
    }
    return reports.filter((r) => r.category === catValue).length;
  };

  const formatFileSize = (bytes: number) => {
    if (!bytes) return "0 KB";
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(0)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        month: "short",
        day: "2-digit",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
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

  const handleGenerateShare = async () => {
    if (reportsToShare.length === 0) return;
    setSharing(true);
    setShareError(null);
    try {
      const targetIds = reportsToShare.map((r) => r.id);
      const share = await createReportShare(targetIds, shareDuration);
      setActiveShare(share);

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

  const allVisibleSelected =
    filteredReports.length > 0 &&
    filteredReports.every((r) => selectedReportIds.includes(r.id));

  return (
    <div className="space-y-6 sm:space-y-7 animate-in fade-in duration-300">
      {/* Page Header with Privacy Assurance Pill */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Medical Records Library
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Find, view and manage all your medical reports in one secure place.
          </p>
        </div>

        {/* Right Privacy Pill */}
        <div className="inline-flex items-center gap-2.5 px-3.5 py-2 rounded-2xl bg-blue-50/80 border border-blue-100 text-xs text-blue-900 self-start md:self-auto shadow-sm">
          <div className="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center flex-shrink-0">
            <Check className="w-3.5 h-3.5 stroke-[3]" />
          </div>
          <div className="leading-tight">
            <span className="font-semibold block text-blue-950">
              Your records are private and secure
            </span>
            <span className="text-[11px] text-blue-700">Only you control what to share</span>
          </div>
        </div>
      </div>

      {/* Action Notification Banner */}
      {actionNotice && (
        <div className="p-3.5 rounded-xl bg-blue-50 border border-blue-200 text-blue-900 text-xs flex items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-blue-600 flex-shrink-0" />
            <span>{actionNotice}</span>
          </div>
          <button
            onClick={() => setActionNotice(null)}
            className="text-blue-700 hover:text-blue-900 font-bold text-xs"
          >
            ✕
          </button>
        </div>
      )}

      {/* Control Bar: Search Input, Sort By, Select All */}
      <div className="bg-white rounded-2xl p-4 sm:p-5 border border-slate-200/80 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
          <input
            type="text"
            placeholder="Search reports by title, type, hospital or keyword..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-3 text-slate-400 hover:text-slate-600 text-xs font-bold"
            >
              ✕
            </button>
          )}
        </div>

        {/* Sort and Select Controls */}
        <div className="flex items-center gap-3 justify-between md:justify-end">
          {/* Sort By Dropdown */}
          <div className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2">
            <span className="text-slate-400 hidden sm:inline">Sort by</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="bg-transparent font-medium text-slate-800 focus:outline-none cursor-pointer"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="title">Title (A-Z)</option>
            </select>
          </div>

          {/* Select All Toggle */}
          <button
            onClick={handleSelectAll}
            className={`flex items-center gap-2 text-xs font-semibold px-3.5 py-2 rounded-xl border transition ${
              allVisibleSelected
                ? "bg-blue-50 border-blue-300 text-blue-700"
                : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
            }`}
          >
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={() => {}}
              className="rounded text-blue-600 focus:ring-0 cursor-pointer pointer-events-none"
            />
            <span>Select All</span>
          </button>
        </div>
      </div>

      {/* Category Filter Pills (Horizontal Scrollable) */}
      <div className="flex items-center gap-2.5 overflow-x-auto pb-1 no-scrollbar">
        {CATEGORIES_LIST.map((cat) => {
          const Icon = cat.icon;
          const isActive = selectedCategory === cat.value;
          const count = getCategoryCount(cat.value);

          return (
            <button
              key={cat.value}
              onClick={() => setSelectedCategory(cat.value)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition border ${
                isActive
                  ? "bg-blue-600 text-white border-blue-600 shadow-sm"
                  : "bg-white text-slate-600 border-slate-200/80 hover:bg-slate-50 hover:border-slate-300"
              }`}
            >
              <Icon
                className={`w-3.5 h-3.5 ${
                  isActive ? "text-white" : cat.colorClass
                }`}
              />
              <span>{cat.label}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono ${
                  isActive
                    ? "bg-white/20 text-white"
                    : "bg-slate-100 text-slate-500"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Reports List View */}
      {loading ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-16 text-center space-y-3 shadow-sm">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
          <p className="text-sm text-slate-600 font-medium">Retrieving medical reports...</p>
        </div>
      ) : errorMsg ? (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-amber-900 space-y-2">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <AlertCircle className="w-5 h-5 text-amber-600" /> Unable to load records
          </div>
          <p className="text-xs text-amber-800">{errorMsg}</p>
        </div>
      ) : filteredReports.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-14 text-center space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mx-auto">
            <FileText className="w-6 h-6 stroke-[1.8]" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-base">No Medical Records Found</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              {searchQuery
                ? `No medical reports matching "${searchQuery}". Try clearing search or choosing another category.`
                : "You have not uploaded any records in this category yet."}
            </p>
          </div>
          <Link
            href="/patient/upload"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition shadow-sm"
          >
            <UploadCloud className="w-4 h-4" /> Upload Medical Report
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredReports.map((report) => {
            const isSelected = selectedReportIds.includes(report.id);
            const categoryInfo = CATEGORY_MAP[report.category] || CATEGORY_MAP.other;
            const CategoryIcon = categoryInfo.icon;

            return (
              <div
                key={report.id}
                className={`bg-white rounded-2xl p-4 sm:p-5 border transition shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4 ${
                  isSelected
                    ? "border-blue-500/80 ring-1 ring-blue-500/20 bg-blue-50/20"
                    : "border-slate-200/80 hover:border-slate-300"
                }`}
              >
                {/* Left Side: Checkbox + Icon + Title + Metadata */}
                <div className="flex items-center gap-3.5 min-w-0 flex-1">
                  {/* Selection Checkbox */}
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelectReport(report.id)}
                    className="w-4 h-4 rounded text-blue-600 focus:ring-0 cursor-pointer flex-shrink-0"
                  />

                  {/* Category Colored Icon */}
                  <div
                    className={`w-11 h-11 rounded-xl ${categoryInfo.iconBgClass} flex items-center justify-center flex-shrink-0 shadow-sm`}
                  >
                    <CategoryIcon className="w-5 h-5" />
                  </div>

                  {/* Title & Report ID */}
                  <div className="min-w-0 flex-1">
                    <h3 className="font-bold text-slate-900 text-sm sm:text-base truncate">
                      {report.title}
                    </h3>
                    <p className="text-xs text-slate-400 font-mono mt-0.5">
                      Report ID: {report.report_id}
                    </p>
                  </div>
                </div>

                {/* Middle Details: Date, Size, Category Badge */}
                <div className="flex items-center gap-5 sm:gap-7 text-xs text-slate-600 pl-7 md:pl-0 flex-shrink-0">
                  {/* Date Column */}
                  <div>
                    <span className="text-[10px] uppercase text-slate-400 block font-medium">
                      Date
                    </span>
                    <span className="font-semibold text-slate-800">
                      {formatDate(report.report_date)}
                    </span>
                  </div>

                  {/* Size Column */}
                  <div>
                    <span className="text-[10px] uppercase text-slate-400 block font-medium">
                      Size
                    </span>
                    <span className="font-semibold text-slate-800">
                      {formatFileSize(report.file_size_bytes)}
                    </span>
                  </div>

                  {/* Category Pill */}
                  <div className="hidden sm:block">
                    <span
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-medium ${categoryInfo.badgeClass}`}
                    >
                      <CategoryIcon className="w-3 h-3" />
                      <span>{categoryInfo.label}</span>
                    </span>
                  </div>
                </div>

                {/* Right Actions: Share QR, View/Download, Delete */}
                <div className="flex items-center gap-2.5 pl-7 md:pl-0 pt-2 md:pt-0 border-t md:border-t-0 border-slate-100 justify-end flex-shrink-0">
                  {/* Share QR Button */}
                  <button
                    onClick={() => openShareModal(report)}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 transition"
                    title="Generate QR code to share"
                  >
                    <QrCode className="w-3.5 h-3.5" />
                    <span>Share QR</span>
                  </button>

                  {/* View / Download Button */}
                  <button
                    onClick={() => handleDownload(report)}
                    disabled={downloadingId === report.id}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 transition shadow-sm disabled:opacity-60"
                  >
                    {downloadingId === report.id ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Opening...</span>
                      </>
                    ) : (
                      <>
                        <Eye className="w-3.5 h-3.5" />
                        <span>View / Download</span>
                      </>
                    )}
                  </button>

                  {/* Delete Button */}
                  <button
                    onClick={() => setReportToDelete(report)}
                    className="p-2 rounded-xl text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition border border-transparent hover:border-rose-100"
                    title="Delete report"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Floating Multi-Report Action Bar (when reports are selected) */}
      {selectedReportIds.length > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-slate-900 text-white rounded-2xl px-5 py-3.5 shadow-2xl flex items-center gap-4 animate-in slide-in-from-bottom-4 duration-200 border border-slate-800">
          <div className="flex items-center gap-2 text-xs sm:text-sm font-semibold">
            <div className="w-5 h-5 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">
              {selectedReportIds.length}
            </div>
            <span>
              {selectedReportIds.length === 1
                ? "1 report selected"
                : `${selectedReportIds.length} reports selected`}
            </span>
          </div>

          <button
            onClick={openShareModalForSelected}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl text-xs sm:text-sm font-bold transition shadow-md"
          >
            <QrCode className="w-4 h-4" />
            <span>Generate Shared QR</span>
          </button>

          <button
            onClick={() => setSelectedReportIds([])}
            className="text-xs text-slate-400 hover:text-white transition underline"
          >
            Clear
          </button>
        </div>
      )}

      {/* Share QR Modal */}
      {reportsToShare.length > 0 && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 sm:p-7 shadow-2xl border border-slate-200 space-y-5 animate-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <QrCode className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base sm:text-lg">
                    {reportsToShare.length > 1
                      ? `Share ${reportsToShare.length} Medical Reports`
                      : "Share Medical Report"}
                  </h3>
                  <p className="text-xs text-slate-500">
                    Expiring, revocable access via QR code
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setReportsToShare([]);
                  setActiveShare(null);
                  setQrDataUrl(null);
                }}
                className="text-slate-400 hover:text-slate-600 text-sm font-bold"
              >
                ✕
              </button>
            </div>

            {/* If Share Not Generated Yet: Duration Selector */}
            {!activeShare ? (
              <div className="space-y-4">
                {/* Reports Summary */}
                <div className="bg-slate-50 rounded-xl p-3 border border-slate-200/80 max-h-32 overflow-y-auto space-y-1.5">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                    Selected Reports
                  </span>
                  {reportsToShare.map((r) => (
                    <div key={r.id} className="text-xs font-semibold text-slate-800 truncate">
                      • {r.title} ({r.category.replace("_", " ")})
                    </div>
                  ))}
                </div>

                {/* Duration Options */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-2">
                    Access Duration
                  </label>
                  <div className="space-y-2">
                    {DURATION_OPTIONS.map((opt) => (
                      <label
                        key={opt.seconds}
                        className={`flex items-center justify-between p-3 rounded-xl border text-xs cursor-pointer transition ${
                          shareDuration === opt.seconds
                            ? "bg-blue-50 border-blue-400 text-blue-900 font-semibold"
                            : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        <span>{opt.label}</span>
                        <input
                          type="radio"
                          name="duration"
                          checked={shareDuration === opt.seconds}
                          onChange={() => setShareDuration(opt.seconds)}
                          className="text-blue-600 focus:ring-0"
                        />
                      </label>
                    ))}
                  </div>
                </div>

                {shareError && (
                  <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl">
                    {shareError}
                  </div>
                )}

                <button
                  onClick={handleGenerateShare}
                  disabled={sharing}
                  className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-bold transition flex items-center justify-center gap-2 shadow-sm disabled:opacity-60"
                >
                  {sharing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Generating Secure QR...</span>
                    </>
                  ) : (
                    <>
                      <QrCode className="w-4 h-4" />
                      <span>Generate QR Code</span>
                    </>
                  )}
                </button>
              </div>
            ) : (
              /* If Share Generated: Display QR Code */
              <div className="space-y-4 text-center">
                <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 inline-block mx-auto shadow-inner">
                  {qrDataUrl && (
                    <img
                      src={qrDataUrl}
                      alt="Medical Report Share QR Code"
                      className="w-56 h-56 mx-auto rounded-lg"
                    />
                  )}
                </div>

                <div className="space-y-1">
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-semibold border border-emerald-200">
                    <Clock className="w-3.5 h-3.5" />
                    <span>
                      Expires in: {Math.round(activeShare.expires_in_seconds / 60)} minutes
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">
                    Clinicians can scan this QR code with any camera or tablet to access authorized reports.
                  </p>
                </div>

                {/* Copy Link Input */}
                <div className="flex gap-2">
                  <input
                    type="text"
                    readOnly
                    value={activeShare.share_url}
                    className="flex-1 px-3 py-2 bg-slate-50 rounded-xl border border-slate-200 text-xs font-mono text-slate-700 select-all"
                  />
                  <button
                    onClick={handleCopyLink}
                    className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition flex items-center gap-1"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copied ? "Copied" : "Copy"}</span>
                  </button>
                </div>

                {/* Revoke Button */}
                <button
                  onClick={handleRevokeShare}
                  disabled={revoking}
                  className="w-full py-2.5 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-xl text-xs font-bold transition border border-rose-200 flex items-center justify-center gap-1.5"
                >
                  {revoking ? "Revoking..." : "Revoke Access Immediately"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {reportToDelete && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-sm w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <div className="w-10 h-10 rounded-full bg-rose-50 flex items-center justify-center">
                <Trash2 className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-slate-900 text-base">Delete Report?</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Are you sure you want to delete{" "}
              <strong className="text-slate-800">"{reportToDelete.title}"</strong>? This will permanently remove the encrypted document and revoke all active share grants.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setReportToDelete(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold transition disabled:opacity-60"
              >
                {deleting ? "Deleting..." : "Confirm Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
