"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import {
  QrCode,
  ShieldCheck,
  Check,
  Copy,
  Clock,
  Loader2,
  AlertCircle,
  FileText,
  UploadCloud,
  CheckCircle2,
  Trash2,
} from "lucide-react";
import {
  getMyReports,
  createReportShare,
  revokeReportShare,
  MedicalReport,
  ShareGrantResponse,
} from "@/lib/api";

const DURATION_OPTIONS = [
  { label: "15 Minutes (Recommended)", seconds: 900 },
  { label: "1 Hour", seconds: 3600 },
  { label: "24 Hours", seconds: 86400 },
];

export default function ShareQRPage() {
  const router = useRouter();
  const [reports, setReports] = useState<MedicalReport[]>([]);
  const [selectedReportIds, setSelectedReportIds] = useState<string[]>([]);
  const [duration, setDuration] = useState<number>(900);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [activeShare, setActiveShare] = useState<ShareGrantResponse | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("med_report_token");
      if (!token || !token.trim()) {
        router.push("/patient/login");
        return;
      }
    }

    const loadReports = async () => {
      setLoading(true);
      setErrorMsg(null);
      try {
        const data = await getMyReports();
        setReports(data || []);
        // Pre-select all reports if available
        if (data && data.length > 0) {
          setSelectedReportIds(data.map((r) => r.id));
        }
      } catch (err: any) {
        setErrorMsg(err.message || "Failed to load medical reports.");
      } finally {
        setLoading(false);
      }
    };

    loadReports();
  }, [router]);

  const toggleSelectReport = (id: string) => {
    setSelectedReportIds((prev) =>
      prev.includes(id) ? prev.filter((rId) => rId !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    if (selectedReportIds.length === reports.length) {
      setSelectedReportIds([]);
    } else {
      setSelectedReportIds(reports.map((r) => r.id));
    }
  };

  const handleGenerateQR = async () => {
    if (selectedReportIds.length === 0) {
      setErrorMsg("Please select at least one medical report to include in this QR share.");
      return;
    }

    setGenerating(true);
    setErrorMsg(null);

    try {
      const share = await createReportShare(selectedReportIds, duration);
      setActiveShare(share);

      const qrUrl = await QRCode.toDataURL(share.share_url, {
        width: 320,
        margin: 2,
        color: {
          dark: "#0f172a",
          light: "#ffffff",
        },
      });
      setQrDataUrl(qrUrl);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to create share grant.");
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = () => {
    if (!activeShare) return;
    navigator.clipboard.writeText(activeShare.share_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRevoke = async () => {
    if (!activeShare) return;
    setRevoking(true);
    try {
      await revokeReportShare(activeShare.grant_id);
      setActiveShare(null);
      setQrDataUrl(null);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to revoke share.");
    } finally {
      setRevoking(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6 sm:space-y-7 animate-in fade-in duration-300">
      {/* Header */}
      <div className="text-center space-y-2">
        <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
          Create Share QR
        </h1>
        <p className="text-sm text-slate-500 max-w-lg mx-auto">
          Generate an encrypted, time-limited QR code for healthcare clinicians to view your selected records.
        </p>

        <div className="pt-2">
          <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-2xl bg-emerald-50 text-xs text-emerald-800 border border-emerald-200 shadow-sm">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Time-Limited Access • Instant Revocation Anytime • Zero Permanent Storage</span>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2.5">
          <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {loading ? (
        <div className="bg-white rounded-3xl border border-slate-200/80 p-16 text-center space-y-3 shadow-sm">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
          <p className="text-sm text-slate-600 font-medium">Loading reports for sharing...</p>
        </div>
      ) : reports.length === 0 ? (
        <div className="bg-white rounded-3xl border border-slate-200/80 p-12 text-center space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mx-auto">
            <FileText className="w-6 h-6 stroke-[1.8]" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-base">No Reports to Share</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              You need to upload at least one medical report before creating a share QR code.
            </p>
          </div>
          <Link
            href="/patient/upload"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition shadow-sm"
          >
            <UploadCloud className="w-4 h-4" /> Upload Report First
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200/80 shadow-sm space-y-6">
          {!activeShare ? (
            /* Step 1: Select Reports & Duration */
            <div className="space-y-6">
              {/* Report Selection List */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-slate-900 text-sm sm:text-base">
                    1. Select Reports to Include
                  </h3>
                  <button
                    type="button"
                    onClick={handleSelectAll}
                    className="text-xs font-semibold text-blue-600 hover:underline"
                  >
                    {selectedReportIds.length === reports.length ? "Deselect All" : "Select All"}
                  </button>
                </div>

                <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                  {reports.map((report) => {
                    const isSelected = selectedReportIds.includes(report.id);
                    return (
                      <label
                        key={report.id}
                        className={`flex items-center justify-between p-3.5 rounded-2xl border transition cursor-pointer ${
                          isSelected
                            ? "bg-blue-50/50 border-blue-400 text-blue-950 font-medium"
                            : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectReport(report.id)}
                            className="w-4 h-4 rounded text-blue-600 focus:ring-0 cursor-pointer"
                          />
                          <div className="min-w-0">
                            <span className="font-bold text-xs sm:text-sm block truncate">
                              {report.title}
                            </span>
                            <span className="text-[11px] text-slate-400 font-mono block">
                              {report.report_id} • {report.report_date}
                            </span>
                          </div>
                        </div>
                        <span className="text-[11px] uppercase font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                          {report.category.replace("_", " ")}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Step 2: Choose Duration */}
              <div className="space-y-3 pt-2 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 text-sm sm:text-base">
                  2. Choose Expiration Duration
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {DURATION_OPTIONS.map((opt) => (
                    <label
                      key={opt.seconds}
                      className={`p-3.5 rounded-2xl border text-xs cursor-pointer text-center transition flex flex-col justify-between ${
                        duration === opt.seconds
                          ? "bg-blue-50 border-blue-500 text-blue-900 font-bold shadow-sm"
                          : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      <input
                        type="radio"
                        name="duration"
                        checked={duration === opt.seconds}
                        onChange={() => setDuration(opt.seconds)}
                        className="hidden"
                      />
                      <span>{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Generate Button */}
              <div className="pt-2">
                <button
                  type="button"
                  onClick={handleGenerateQR}
                  disabled={generating || selectedReportIds.length === 0}
                  className="w-full py-3.5 bg-blue-600 hover:bg-blue-700 text-white rounded-2xl text-sm font-bold transition flex items-center justify-center gap-2 shadow-md disabled:opacity-50"
                >
                  {generating ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Creating Secure Grant...</span>
                    </>
                  ) : (
                    <>
                      <QrCode className="w-5 h-5" />
                      <span>
                        Generate Share QR Code ({selectedReportIds.length} Reports)
                      </span>
                    </>
                  )}
                </button>
              </div>
            </div>
          ) : (
            /* Active QR Display View */
            <div className="space-y-6 text-center animate-in zoom-in-95 duration-200">
              <div className="p-4 bg-slate-50 rounded-3xl border border-slate-200 inline-block mx-auto shadow-inner">
                {qrDataUrl && (
                  <img
                    src={qrDataUrl}
                    alt="Medical Share QR Code"
                    className="w-64 h-64 mx-auto rounded-xl"
                  />
                )}
              </div>

              <div className="space-y-1.5">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-semibold border border-emerald-200">
                  <Clock className="w-3.5 h-3.5" />
                  <span>
                    Expires in: {Math.round(activeShare.expires_in_seconds / 60)} minutes
                  </span>
                </div>
                <h4 className="font-bold text-slate-900 text-sm">
                  Active Share Session for {activeShare.reports_count} Medical Report(s)
                </h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Hold this QR code up for your doctor to scan, or copy the direct secure link below.
                </p>
              </div>

              {/* Copy Direct Link */}
              <div className="flex gap-2 max-w-md mx-auto">
                <input
                  type="text"
                  readOnly
                  value={activeShare.share_url}
                  className="flex-1 px-3.5 py-2.5 bg-slate-50 rounded-xl border border-slate-200 text-xs font-mono text-slate-700 select-all"
                />
                <button
                  onClick={handleCopy}
                  className="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? "Copied" : "Copy Link"}</span>
                </button>
              </div>

              {/* Action Buttons: Revoke or Create New */}
              <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
                <button
                  onClick={handleRevoke}
                  disabled={revoking}
                  className="w-full sm:w-auto px-5 py-2.5 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-xl text-xs font-bold transition border border-rose-200 flex items-center justify-center gap-1.5"
                >
                  {revoking ? "Revoking..." : "Revoke Access Immediately"}
                </button>

                <button
                  onClick={() => {
                    setActiveShare(null);
                    setQrDataUrl(null);
                  }}
                  className="w-full sm:w-auto px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition"
                >
                  Create Another Share
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
