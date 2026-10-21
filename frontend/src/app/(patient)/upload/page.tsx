"use client";

import React, { useState, useRef, useEffect } from "react";
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
  Calendar,
  Check,
  Sparkles,
  Lock,
  Image as ImageIcon,
} from "lucide-react";
import { uploadMedicalReport } from "@/lib/api";

const CATEGORIES = [
  { value: "blood_test", label: "Lab Report / Blood Test" },
  { value: "xray", label: "Radiology / X-Ray Scan" },
  { value: "ct_scan", label: "CT Scan" },
  { value: "mri", label: "MRI Scan" },
  { value: "prescription", label: "Prescription" },
  { value: "discharge_summary", label: "Discharge Summary" },
  { value: "other", label: "Other Diagnostic / Clinical" },
];

const MAX_FILE_SIZE_BYTES = 40 * 1024 * 1024; // 40 MB
const ALLOWED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"];
const ALLOWED_MIME_TYPES = ["application/pdf", "image/jpeg", "image/png"];

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
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const todayStr = new Date().toISOString().split("T")[0];

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("med_report_token");
      if (!token || !token.trim()) {
        router.push("/patient/login");
      }
    }
  }, [router]);

  const handleFileValidation = (file: File) => {
    setErrorMsg(null);
    setSuccessMsg(null);

    // Validate extension
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setErrorMsg("Invalid file format. Only PDF documents (.pdf) and photos (.jpg, .jpeg, .png) are permitted.");
      return false;
    }

    // Validate MIME type
    if (file.type && !ALLOWED_MIME_TYPES.includes(file.type.toLowerCase())) {
      setErrorMsg("Invalid file type. Allowed formats: PDF, JPEG, or PNG.");
      return false;
    }

    // Validate size
    if (file.size === 0) {
      setErrorMsg("The selected file is empty (0 bytes).");
      return false;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
      setErrorMsg(`File size (${sizeMb} MB) exceeds maximum allowed limit of 40 MB.`);
      return false;
    }

    setSelectedFile(file);
    // Auto-fill title if empty
    if (!title.trim()) {
      const cleanName = file.name
        .replace(/\.[^/.]+$/, "")
        .replace(/[_-]+/g, " ")
        .replace(/\b\w/g, (l) => l.toUpperCase());
      setTitle(cleanName);
    }
    setUploadProgress(100);
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
      setErrorMsg("Please select a file (PDF or photo) to upload.");
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
        `Report "${created.title}" successfully uploaded and encrypted. Assigned ID: ${created.report_id}.`
      );

      // Reset form
      setSelectedFile(null);
      setTitle("");
      setDescription("");
      if (fileInputRef.current) fileInputRef.current.value = "";

      // Smooth navigation after 1.5s
      setTimeout(() => {
        router.push("/patient/reports");
      }, 1500);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to upload medical report.");
    } finally {
      setUploading(false);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6 sm:space-y-7 animate-in fade-in duration-300">
      {/* Centered Page Header */}
      <div className="text-center space-y-2">
        <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
          Upload Medical Report
        </h1>
        <p className="text-sm text-slate-500 max-w-lg mx-auto">
          Add your medical reports and test results to keep your health records in one secure place.
        </p>

        {/* Security Assurance Banner */}
        <div className="pt-2">
          <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-2xl bg-blue-50/80 border border-blue-100 text-xs text-blue-900 shadow-sm">
            <div className="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center flex-shrink-0">
              <Check className="w-3.5 h-3.5 stroke-[3]" />
            </div>
            <span>
              Your files are encrypted and stored securely. Only you can access your medical information.
            </span>
          </div>
        </div>
      </div>

      {/* Main Form Card Container */}
      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200/80 shadow-sm space-y-6">
        {/* Error / Success Feedback */}
        {errorMsg && (
          <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-3">
            <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-3">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Drag & Drop Area */}
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-3xl p-8 sm:p-10 text-center transition cursor-pointer relative overflow-hidden ${
              dragActive
                ? "border-blue-500 bg-blue-50/50"
                : "border-blue-200/90 bg-blue-50/20 hover:bg-blue-50/40 hover:border-blue-300"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,image/jpeg,image/png,application/pdf"
              onChange={handleFileChange}
              className="hidden"
            />

            <div className="flex flex-col items-center justify-center space-y-3">
              {/* Cloud Icon */}
              <div className="w-14 h-14 rounded-2xl bg-blue-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20">
                <UploadCloud className="w-7 h-7 stroke-[2.2]" />
              </div>

              <div>
                <p className="text-base font-bold text-slate-900">
                  Drag and drop your report or medical photo here
                </p>
                <p className="text-xs text-blue-600 font-semibold mt-1">
                  or click to browse files
                </p>
              </div>

              <p className="text-[11px] text-slate-400">
                PDF, JPEG, or PNG files up to 40 MB.
              </p>
            </div>
          </div>

          {/* Selected File Progress / Ready Banner */}
          {selectedFile && (
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 border ${
                  selectedFile.type.startsWith("image/") || /\.(jpg|jpeg|png)$/i.test(selectedFile.name)
                    ? "bg-indigo-50 text-indigo-600 border-indigo-100"
                    : "bg-rose-50 text-rose-600 border-rose-100"
                }`}>
                  {selectedFile.type.startsWith("image/") || /\.(jpg|jpeg|png)$/i.test(selectedFile.name) ? (
                    <ImageIcon className="w-5 h-5" />
                  ) : (
                    <FileText className="w-5 h-5" />
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-bold text-slate-900 truncate">
                    {selectedFile.name}
                  </p>
                  <p className="text-[11px] text-slate-400">
                    {formatFileSize(selectedFile.size)}
                  </p>
                </div>
              </div>

              {/* Progress and status */}
              <div className="flex items-center gap-3 flex-1 sm:max-w-xs">
                <div className="flex-1 h-2 rounded-full bg-slate-200 overflow-hidden">
                  <div
                    className="h-full bg-blue-600 rounded-full transition-all duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 whitespace-nowrap">
                  <span>Upload ready</span>
                  <div className="w-4 h-4 rounded-full bg-emerald-500 text-white flex items-center justify-center">
                    <Check className="w-2.5 h-2.5 stroke-[3]" />
                  </div>
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  className="text-slate-400 hover:text-slate-600 p-1"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* Metadata Form Fields */}
          <div className="space-y-4 pt-1">
            {/* Row 1: Report Title and Category */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1.5">
                  Report Title <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Annual Blood Test Report"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1.5">
                  Category <span className="text-rose-500">*</span>
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition cursor-pointer"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Row 2: Report / Test Date */}
            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1.5">
                Report / Test Date <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <input
                  type="date"
                  max={todayStr}
                  value={reportDate}
                  onChange={(e) => setReportDate(e.target.value)}
                  required
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition"
                />
              </div>
            </div>

            {/* Row 3: Clinical Notes (Optional) */}
            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1.5">
                Clinical Notes (Optional)
              </label>
              <textarea
                rows={3}
                placeholder="e.g. Routine annual blood test. All values within normal range."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition"
              />
            </div>
          </div>

          {/* Action Footer Buttons */}
          <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={() => router.push("/patient/reports")}
              className="px-5 py-2.5 rounded-xl border border-slate-200 text-xs sm:text-sm font-semibold text-slate-700 hover:bg-slate-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={uploading || !selectedFile}
              className="px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs sm:text-sm font-bold transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Encrypting & Uploading...</span>
                </>
              ) : (
                <span>Upload Medical Report</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
