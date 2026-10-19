import React from "react";
import Link from "next/link";
import { FileText, UploadCloud, Share2, Shield, User, ArrowLeft } from "lucide-react";

export default function PatientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="text-slate-500 hover:text-slate-800 transition flex items-center gap-1.5 text-sm">
              <ArrowLeft className="w-4 h-4" /> Home
            </Link>
            <span className="h-5 w-px bg-slate-200" />
            <span className="font-semibold text-slate-900 flex items-center gap-2">
              <Shield className="w-5 h-5 text-blue-600" /> My Health Records
            </span>
          </div>

          <div className="flex items-center gap-2 sm:gap-4 text-sm font-medium">
            <Link
              href="/patient/dashboard"
              className="px-3 py-1.5 text-slate-700 hover:text-blue-600 rounded-md transition"
            >
              Dashboard
            </Link>
            <Link
              href="/patient/reports"
              className="px-3 py-1.5 text-slate-700 hover:text-blue-600 rounded-md transition"
            >
              Reports
            </Link>
            <Link
              href="/patient/upload"
              className="px-3 py-1.5 text-slate-700 hover:text-blue-600 rounded-md transition"
            >
              Upload
            </Link>
            <Link
              href="/patient/share"
              className="px-3 py-1.5 text-slate-700 hover:text-blue-600 rounded-md transition"
            >
              Share QR
            </Link>
          </div>
        </div>
      </nav>

      <main className="flex-1 max-w-6xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
