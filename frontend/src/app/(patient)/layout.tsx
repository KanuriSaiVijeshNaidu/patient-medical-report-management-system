"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Shield, ArrowLeft, LogOut } from "lucide-react";
import { signOutPatient } from "@/lib/supabaseClient";

export default function PatientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [signingOut, setSigningOut] = useState<boolean>(false);

  useEffect(() => {
    const checkAuth = () => {
      if (typeof window !== "undefined") {
        const token = localStorage.getItem("med_report_token");
        setIsAuthenticated(Boolean(token && token.trim()));
      }
    };

    checkAuth();

    window.addEventListener("auth-state-change", checkAuth);
    window.addEventListener("storage", checkAuth);

    return () => {
      window.removeEventListener("auth-state-change", checkAuth);
      window.removeEventListener("storage", checkAuth);
    };
  }, []);

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await signOutPatient();
      setIsAuthenticated(false);
      router.push("/patient/login");
    } finally {
      setSigningOut(false);
    }
  };

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

          <div className="flex items-center gap-2 sm:gap-3 text-sm font-medium">
            {isAuthenticated ? (
              <>
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
                <button
                  onClick={handleSignOut}
                  disabled={signingOut}
                  className="px-3 py-1.5 text-rose-600 hover:text-rose-700 hover:bg-rose-50 rounded-md border border-rose-200 flex items-center gap-1.5 transition text-xs font-semibold"
                  title="Sign out of your session"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>{signingOut ? "Signing out..." : "Sign Out"}</span>
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/patient/login"
                  className="px-3 py-1.5 text-slate-700 hover:text-blue-600 rounded-md transition"
                >
                  Sign In
                </Link>
                <Link
                  href="/patient/register"
                  className="px-3 py-1.5 text-white bg-blue-600 hover:bg-blue-700 rounded-md transition font-semibold"
                >
                  Register
                </Link>
              </>
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
