import React from "react";
import Link from "next/link";
import { QrCode, Upload, FileText, Clock, ShieldAlert, CheckCircle2 } from "lucide-react";

export default function PatientDashboardPage() {
  return (
    <div className="space-y-8">
      {/* Patient Identity Banner */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-2xl p-6 sm:p-8 text-white shadow-md flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/20 text-xs font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> Identity Verified
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold">Welcome, Patient</h1>
          <p className="text-blue-100 text-sm max-w-xl">
            Your unique Patient ID provides authenticated access for authorized hospitals and enables instant emergency record retrieval.
          </p>
        </div>

        <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl p-4 text-center min-w-[220px]">
          <span className="text-xs uppercase tracking-wider text-blue-200 font-semibold block">Permanent Patient ID</span>
          <span className="text-2xl font-mono font-bold tracking-wide mt-1 block">MED-2026-894102</span>
          <span className="text-[11px] text-blue-200 mt-1 block">Present this ID at hospital registration</span>
        </div>
      </div>

      {/* Quick Action Grid */}
      <div className="grid sm:grid-cols-3 gap-4">
        <Link
          href="/patient/upload"
          className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:border-blue-400 transition group"
        >
          <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center mb-3 group-hover:scale-105 transition">
            <Upload className="w-5 h-5" />
          </div>
          <h3 className="font-semibold text-slate-900">Upload New Report</h3>
          <p className="text-xs text-slate-500 mt-1">Upload blood tests, MRI scans, X-rays, or prescriptions.</p>
        </Link>

        <Link
          href="/patient/share"
          className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:border-blue-400 transition group"
        >
          <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center mb-3 group-hover:scale-105 transition">
            <QrCode className="w-5 h-5" />
          </div>
          <h3 className="font-semibold text-slate-900">Create Share QR</h3>
          <p className="text-xs text-slate-500 mt-1">Generate a time-bound, revocable link for doctor review.</p>
        </Link>

        <Link
          href="/patient/reports"
          className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:border-blue-400 transition group"
        >
          <div className="w-10 h-10 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center mb-3 group-hover:scale-105 transition">
            <FileText className="w-5 h-5" />
          </div>
          <h3 className="font-semibold text-slate-900">Medical Library</h3>
          <p className="text-xs text-slate-500 mt-1">View categorized history and lab-verified records.</p>
        </Link>
      </div>

      {/* Architecture Review Notice */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-amber-800 flex items-start gap-3">
        <ShieldAlert className="w-5 h-5 mt-0.5 flex-shrink-0 text-amber-600" />
        <div className="text-sm">
          <p className="font-semibold">Phase 1 Architecture Foundation</p>
          <p className="mt-0.5 text-amber-700">
            UI pages are structured to demonstrate the complete patient workflow. Real data fetching and Supabase upload integration will be connected after architectural approval.
          </p>
        </div>
      </div>
    </div>
  );
}
