"use client";

import React, { useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  UploadCloud,
  FileText,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ArrowLeft,
  X,
  FileCheck,
  ShieldCheck,
} from "lucide-react";
import { uploadMedicalReport } from "@/lib/api";

const CATEGORIES = [
  { value: "blood_test", label: "Blood Test" },
  { value: "xray", label: "X-Ray Scan" },
  { value: "ct_scan", label: "CT Scan" },
  { value: "mri", label: "MRI Scan" },
  { value: "prescription", label: "Prescription" },
  { value: "discharge_summary", label: "Discharge Summary" },
  { value: "other", label: "Other Diagnostic / Lab" },
];

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

export default function UploadReportPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("blood_test");
  const [reportDate, setReportDate] = useState(() => {
    return new Date().toISOString().split("T")[0];
  });
  const [description, setDescription] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const todayStr = new Date().toISOString().split("T")[0];

  React.useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("med_report_token");
      if (!token || !token.trim()) {
        router.push("/patient/login");
      }
    }
  }, [router]);

  const handleFileValidation = (file: File) => {
    setErrorMsg(null);

    // Validate extension
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setErrorMsg("Invalid file format. Only PDF documents (.pdf) are permitted.");
      return false;
    }

    // Validate MIME type
    if (file.type && file.type !== "application/pdf") {
      setErrorMsg("File MIME type must be application/pdf.");
      return false;
    }

    // Validate size
    if (file.size === 0) {
      setErrorMsg("The selected file is empty (0 bytes).");
      return false;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
      setErrorMsg(`File size (${sizeMb} MB) exceeds maximum allowed limit of 10 MB.`);
      return false;
    }

    setSelectedFile(file);
    return true;
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileValidation(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileValidation(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    // Form validations
    if (!title.trim() || title.trim().length < 3) {
      setErrorMsg("Report title must be at least 3 characters long.");
      return;
    }

    if (title.trim().length > 255) {
      setErrorMsg("Report title cannot exceed 255 characters.");
      return;
    }

    if (!reportDate) {
      setErrorMsg("Please select the date when this report or consultation occurred.");
      return;
    }

    if (reportDate > todayStr) {
      setErrorMsg("Report date cannot be in the future.");
      return;
    }

    if (!selectedFile) {
      setErrorMsg("Please select a PDF document to upload.");
      return;
    }

    setUploading(true);

    try {
      const created = await uploadMedicalReport({
        file: selectedFile,
        title: title.trim(),
        category,
        report_date: reportDate,
        description: description.trim() || undefined,
      });

      setSuccessMsg(
        `Report "${created.title}" (${created.report_id}) uploaded securely. Redirecting to reports library...`
      );

      setTimeout(() => {
        router.push("/reports");
      }, 1500);
    } catch (err: any) {
      if (
        err.message?.includes("Authentication required") ||
        err.message?.includes("401") ||
        err.message?.includes("sign in")
      ) {
        router.push("/patient/login");
        return;
      }
      setErrorMsg(err.message || "Failed to upload medical report.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header Breadcrumb */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-4">
        <div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-blue-600 transition mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back to Dashboard
          </Link>
          <h1 className="text-2xl font-bold text-slate-900">Upload Medical Report</h1>
          <p className="text-xs text-slate-500">
            Securely upload diagnostic reports, laboratory panels, imaging, or prescriptions.
          </p>
        </div>
      </div>

      {/* Security Notice */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-start gap-3 text-xs text-blue-900">
        <ShieldCheck className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-semibold">Private & Tamper-Proof Storage</p>
          <p className="text-blue-800 leading-relaxed">
            All documents are stored in an encrypted private storage bucket. Only authorized users
            can view files using time-limited, expiring tokens. Raw paths are never published.
          </p>
        </div>
      </div>

      {/* Notifications */}
      {errorMsg && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start gap-3 text-rose-900 text-xs">
          <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold">Upload Failed:</span> {errorMsg}
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-500 hover:text-rose-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {successMsg && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-start gap-3 text-emerald-900 text-xs">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 font-semibold">{successMsg}</div>
        </div>
      )}

      {/* Upload Form */}
      <form onSubmit={handleSubmit} className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 space-y-6 shadow-sm">
        {/* PDF File Dropzone */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-2">
            PDF Document <span className="text-rose-500">*</span>
          </label>
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition flex flex-col items-center justify-center gap-3 ${
              dragActive
                ? "border-blue-500 bg-blue-50/50"
                : selectedFile
                ? "border-emerald-400 bg-emerald-50/30"
                : "border-slate-300 hover:border-blue-400 hover:bg-slate-50"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf,.pdf"
              onChange={handleFileChange}
              className="hidden"
            />

            {selectedFile ? (
              <div className="flex items-center gap-3 text-left w-full max-w-md p-3 bg-white rounded-lg border border-emerald-200 shadow-sm">
                <FileCheck className="w-8 h-8 text-emerald-600 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900 truncate">{selectedFile.name}</p>
                  <p className="text-xs text-slate-500">
                    {(selectedFile.size / 1024).toFixed(1)} KB • application/pdf
                  </p>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                  }}
                  className="p-1 text-slate-400 hover:text-rose-600 rounded"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <>
                <div className="w-12 h-12 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-800">
                    Click to select or drag and drop your PDF
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    PDF files only, up to 10 MB. Must contain valid %PDF- signature.
                  </p>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Title */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
            Report Title <span className="text-rose-500">*</span>
          </label>
          <input
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Complete Blood Count (CBC) Panel, Lumbar MRI"
            maxLength={255}
            className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
          />
        </div>

        {/* Category & Date Grid */}
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Category <span className="text-rose-500">*</span>
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
            >
              {CATEGORIES.map((cat) => (
                <option key={cat.value} value={cat.value}>
                  {cat.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Report / Test Date <span className="text-rose-500">*</span>
            </label>
            <input
              type="date"
              required
              max={todayStr}
              value={reportDate}
              onChange={(e) => setReportDate(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
            />
            <span className="text-[11px] text-slate-500 block mt-1">
              Cannot be set in the future.
            </span>
          </div>
        </div>

        {/* Optional Description / Clinical Notes */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
            Clinical Notes / Doctor Recommendations (Optional)
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Add relevant notes, diagnostic lab name, prescribing doctor, or symptom context..."
            className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
          />
        </div>

        {/* Action Buttons */}
        <div className="pt-2 border-t border-slate-100 flex items-center justify-end gap-3">
          <Link
            href="/dashboard"
            className="px-4 py-2.5 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
          >
            Cancel
          </Link>
          <button
            type="submit"
            disabled={uploading}
            className="px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition flex items-center gap-2 shadow-sm disabled:opacity-60"
          >
            {uploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Uploading & Securing...
              </>
            ) : (
              <>
                <UploadCloud className="w-4 h-4" /> Upload Medical Report
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
