"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  HeartPulse,
  LayoutDashboard,
  FileText,
  UploadCloud,
  QrCode,
  LogOut,
  ChevronDown,
  User,
  Menu,
  X,
} from "lucide-react";
import { signOutPatient } from "@/lib/supabaseClient";
import { getMyProfile, PatientProfile } from "@/lib/api";

export default function PatientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [signingOut, setSigningOut] = useState<boolean>(false);
  const [profile, setProfile] = useState<PatientProfile | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);

  useEffect(() => {
    const checkAuth = async () => {
      if (typeof window !== "undefined") {
        const token = localStorage.getItem("med_report_token");
        const authed = Boolean(token && token.trim());
        setIsAuthenticated(authed);
        if (authed) {
          try {
            const data = await getMyProfile();
            setProfile(data);
          } catch {
            // Profile fetch optional for nav
          }
        } else {
          setProfile(null);
        }
      }
    };

    checkAuth();

    window.addEventListener("auth-state-change", checkAuth);
    window.addEventListener("storage", checkAuth);

    return () => {
      window.removeEventListener("auth-state-change", checkAuth);
      window.removeEventListener("storage", checkAuth);
    };
  }, [pathname]);

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await signOutPatient();
      setIsAuthenticated(false);
      setProfile(null);
      router.push("/patient/login");
    } finally {
      setSigningOut(false);
    }
  };

  const navItems = [
    { href: "/patient/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/patient/reports", label: "Reports", icon: FileText },
    { href: "/patient/upload", label: "Upload", icon: UploadCloud },
    { href: "/patient/share", label: "Share QR", icon: QrCode },
  ];

  const getInitials = (name?: string) => {
    if (!name) return "PT";
    const parts = name.trim().split(" ");
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F8FAFC]">
      {/* Top Patient Navigation Bar */}
      <header className="bg-white border-b border-slate-200/80 sticky top-0 z-30 shadow-[0_1px_3px_rgba(0,0,0,0.02)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Logo & Brand */}
          <Link
            href="/patient/dashboard"
            className="flex items-center gap-2.5 group transition"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-sm shadow-blue-500/20 group-hover:scale-105 transition">
              <HeartPulse className="w-5 h-5" />
            </div>
            <span className="font-bold text-slate-900 text-lg tracking-tight">
              My Health Records
            </span>
          </Link>

          {/* Desktop Center Navigation Links */}
          {isAuthenticated && (
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href || (item.href !== "/patient/dashboard" && pathname.startsWith(item.href));
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-medium transition ${
                      isActive
                        ? "bg-blue-50 text-blue-600 font-semibold"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                    }`}
                  >
                    <Icon
                      className={`w-4 h-4 ${
                        isActive ? "text-blue-600" : "text-slate-400 group-hover:text-slate-600"
                      }`}
                    />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          )}

          {/* Right Header Section (User Avatar & Sign Out) */}
          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <div className="flex items-center gap-2.5">
                {/* User Pill */}
                <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-full border border-slate-200/80 bg-slate-50/60 hover:bg-slate-100/60 transition cursor-default">
                  <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shadow-inner">
                    {getInitials(profile?.full_name)}
                  </div>
                  <span className="text-xs font-semibold text-slate-800 max-w-[120px] truncate hidden sm:inline">
                    {profile?.full_name || "Patient"}
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400 hidden sm:inline" />
                </div>

                {/* Sign Out Action */}
                <button
                  onClick={handleSignOut}
                  disabled={signingOut}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-rose-600 hover:bg-rose-50 border border-slate-200 hover:border-rose-200 transition"
                  title="Sign out of your session"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">
                    {signingOut ? "Logging out..." : "Logout"}
                  </span>
                </button>

                {/* Mobile Menu Toggle */}
                <button
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="md:hidden p-2 rounded-lg text-slate-600 hover:bg-slate-100 transition"
                  aria-label="Toggle menu"
                >
                  {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm font-medium">
                <Link
                  href="/patient/login"
                  className="px-3.5 py-1.5 text-slate-700 hover:text-blue-600 rounded-lg transition"
                >
                  Sign In
                </Link>
                <Link
                  href="/patient/register"
                  className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition font-semibold shadow-sm"
                >
                  Register
                </Link>
              </div>
            )}
          </div>
        </div>

        {/* Mobile Navigation Dropdown */}
        {isAuthenticated && mobileMenuOpen && (
          <div className="md:hidden border-t border-slate-200 bg-white px-4 pt-2 pb-4 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium ${
                    isActive ? "bg-blue-50 text-blue-600 font-semibold" : "text-slate-600"
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? "text-blue-600" : "text-slate-400"}`} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        )}
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
