"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Building2, Search, AlertOctagon, ArrowLeft, LogOut, UserCheck } from "lucide-react";
import { getHospitalStaffInfo, clearHospitalStaffAuth, HospitalStaffLoginResult } from "@/lib/api";

export default function HospitalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [staff, setStaff] = useState<HospitalStaffLoginResult | null>(null);

  useEffect(() => {
    const updateStaff = () => {
      setStaff(getHospitalStaffInfo());
    };

    updateStaff();
    window.addEventListener("hospital-auth-change", updateStaff);
    window.addEventListener("storage", updateStaff);

    return () => {
      window.removeEventListener("hospital-auth-change", updateStaff);
      window.removeEventListener("storage", updateStaff);
    };
  }, []);

  const handleSignOut = () => {
    clearHospitalStaffAuth();
    setStaff(null);
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-100">
      <nav className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4 sm:gap-6">
            <Link href="/" className="text-slate-400 hover:text-white transition flex items-center gap-1.5 text-sm">
              <ArrowLeft className="w-4 h-4" /> Home
            </Link>
            <span className="h-5 w-px bg-slate-700" />
            <Link href="/hospital/lookup" className="font-semibold flex items-center gap-2 text-white hover:text-slate-200">
              <Building2 className="w-5 h-5 text-emerald-400" /> Hospital Staff Portal
            </Link>
          </div>

          <div className="flex items-center gap-2 sm:gap-4 text-sm font-medium">
            <Link
              href="/hospital/lookup"
              className="px-3 py-1.5 text-slate-300 hover:text-white rounded-md transition flex items-center gap-1.5"
            >
              <Search className="w-4 h-4 text-slate-400" /> Patient Lookup
            </Link>
            <Link
              href="/hospital/emergency"
              className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-md transition flex items-center gap-1 text-xs font-semibold uppercase tracking-wider"
            >
              <AlertOctagon className="w-4 h-4" /> Emergency
            </Link>

            {staff && (
              <div className="flex items-center gap-2 pl-2 border-l border-slate-700">
                <div className="hidden sm:flex flex-col text-right">
                  <span className="text-xs font-semibold text-emerald-300 flex items-center gap-1 justify-end">
                    <UserCheck className="w-3 h-3" /> {staff.staff_name}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono truncate max-w-[140px]">
                    {staff.hospital_name}
                  </span>
                </div>
                <button
                  onClick={handleSignOut}
                  className="p-1.5 sm:px-2.5 sm:py-1 text-xs text-rose-300 hover:text-white hover:bg-rose-900/40 border border-rose-800/60 rounded-md transition flex items-center gap-1"
                  title="Sign out of hospital staff session"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Sign Out</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      <main className="flex-1 max-w-6xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
