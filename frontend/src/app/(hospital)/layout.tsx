"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2,
  Search,
  AlertOctagon,
  ArrowLeft,
  LogOut,
  UserCheck,
  Shield,
  Lock,
} from "lucide-react";
import {
  getHospitalStaffInfo,
  clearHospitalStaffAuth,
  HospitalStaffLoginResult,
} from "@/lib/api";

export default function HospitalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
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
  }, [pathname]);

  const handleSignOut = () => {
    clearHospitalStaffAuth();
    setStaff(null);
  };

  const getInitials = (name?: string) => {
    if (!name) return "DR";
    const parts = name.trim().split(" ");
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F4F7FB]">
      {/* Top Clinician & Hospital Navigation Bar */}
      <nav className="bg-[#0F172A] text-white border-b border-slate-800/80 sticky top-0 z-30 shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Left: Hospital Name & Portal Identity */}
          <div className="flex items-center gap-3 sm:gap-6">
            <Link
              href="/"
              className="text-slate-400 hover:text-white transition flex items-center gap-1.5 text-xs sm:text-sm font-medium"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Home</span>
            </Link>

            <span className="h-4 w-px bg-slate-700 hidden sm:inline" />

            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center font-bold text-sm">
                +
              </div>
              <div className="leading-tight">
                <span className="font-bold text-white text-xs sm:text-sm block tracking-tight">
                  {staff ? staff.hospital_name : "Hospital Staff Portal"}
                </span>
                <span className="text-[10px] text-slate-400 block font-mono">
                  Medical Records Portal
                </span>
              </div>
            </div>
          </div>

          {/* Center Links (Shown when logged in or desktop) */}
          {staff ? (
            <div className="hidden lg:flex items-center gap-2 text-xs font-semibold">
              <Link
                href="/lookup"
                className="px-3.5 py-1.5 bg-blue-600/30 text-blue-200 border border-blue-500/30 rounded-lg flex items-center gap-1.5 transition"
              >
                <Search className="w-3.5 h-3.5 text-blue-300" />
                <span>Patient Lookup</span>
              </Link>
              <Link
                href="/emergency"
                className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider transition"
              >
                <AlertOctagon className="w-3.5 h-3.5" />
                <span>+ Emergency</span>
              </Link>
            </div>
          ) : (
            <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-400 font-medium">
              <Lock className="w-3.5 h-3.5 text-emerald-400" />
              <span>Secure • Authorized Access Only</span>
            </div>
          )}

          {/* Right Section: Clinician Profile & Sign Out */}
          <div className="flex items-center gap-3">
            {staff ? (
              <div className="flex items-center gap-3">
                {/* Clinician Avatar & Title */}
                <div className="flex items-center gap-2.5 text-right">
                  <div className="w-8 h-8 rounded-full bg-slate-800 text-emerald-300 border border-slate-700 flex items-center justify-center font-bold text-xs">
                    {getInitials(staff.staff_name)}
                  </div>
                  <div className="hidden sm:flex flex-col">
                    <span className="text-xs font-bold text-white">
                      {staff.staff_name}
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Consultant Physician
                    </span>
                  </div>
                </div>

                {/* Sign Out Action */}
                <button
                  onClick={handleSignOut}
                  className="px-2.5 py-1.5 text-xs text-rose-300 hover:text-white hover:bg-rose-950/40 border border-rose-900/60 rounded-lg transition flex items-center gap-1"
                  title="Sign out of hospital portal"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Sign Out</span>
                </button>
              </div>
            ) : (
              <Link
                href="/lookup"
                className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition shadow-sm"
              >
                Clinician Sign In
              </Link>
            )}
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
