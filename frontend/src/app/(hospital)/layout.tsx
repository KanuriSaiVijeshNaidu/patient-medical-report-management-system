import React from "react";
import Link from "next/link";
import { Building2, Search, AlertOctagon, ArrowLeft, Shield } from "lucide-react";

export default function HospitalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-100">
      <nav className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="text-slate-400 hover:text-white transition flex items-center gap-1.5 text-sm">
              <ArrowLeft className="w-4 h-4" /> Home
            </Link>
            <span className="h-5 w-px bg-slate-700" />
            <span className="font-semibold flex items-center gap-2">
              <Building2 className="w-5 h-5 text-emerald-400" /> Hospital Staff Portal
            </span>
          </div>

          <div className="flex items-center gap-2 sm:gap-4 text-sm font-medium">
            <Link
              href="/hospital/lookup"
              className="px-3 py-1.5 text-slate-300 hover:text-white rounded-md transition flex items-center gap-1"
            >
              <Search className="w-4 h-4" /> Patient Lookup
            </Link>
            <Link
              href="/hospital/emergency"
              className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-md transition flex items-center gap-1 text-xs font-semibold uppercase tracking-wider"
            >
              <AlertOctagon className="w-4 h-4" /> Emergency Access
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
