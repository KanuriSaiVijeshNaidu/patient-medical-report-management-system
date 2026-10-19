import Link from "next/link";
import { ShieldCheck, FileText, Building2, AlertTriangle, QrCode } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 p-6 md:p-12">
      <div className="max-w-5xl mx-auto space-y-12">
        {/* Header */}
        <header className="text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-sm font-medium">
            <ShieldCheck className="w-4 h-4" /> Secure Medical Record Infrastructure
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-slate-900">
            Patient Medical Report Management System
          </h1>
          <p className="text-lg text-slate-600 max-w-2xl mx-auto">
            A unified, privacy-first healthcare platform giving patients full custody of diagnostic records while enabling verified hospital collaboration and zero-delay emergency access.
          </p>
        </header>

        {/* Portal Cards */}
        <div className="grid md:grid-cols-2 gap-6">
          {/* Patient Portal Card */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 flex flex-col justify-between hover:border-blue-400 transition-all">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600">
                <FileText className="w-6 h-6" />
              </div>
              <h2 className="text-2xl font-bold text-slate-900">Patient Portal</h2>
              <p className="text-slate-600 leading-relaxed">
                Log in via Phone OTP to view and organize your blood tests, MRI/CT scans, prescriptions, and discharge summaries. Generate revocable QR codes for doctor visits.
              </p>
              <ul className="text-sm text-slate-500 space-y-1">
                <li>• Permanent unique Patient ID</li>
                <li>• Granular, time-bound QR code sharing</li>
                <li>• Safe recovery on phone number change</li>
              </ul>
            </div>
            <div className="mt-8 pt-4 border-t border-slate-100">
              <Link
                href="/patient/dashboard"
                className="inline-flex w-full justify-center items-center px-4 py-2.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
              >
                Access Patient Dashboard
              </Link>
            </div>
          </div>

          {/* Hospital Staff Portal Card */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 flex flex-col justify-between hover:border-slate-400 transition-all">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600">
                <Building2 className="w-6 h-6" />
              </div>
              <h2 className="text-2xl font-bold text-slate-900">Hospital Staff Portal</h2>
              <p className="text-slate-600 leading-relaxed">
                Authorized clinicians and diagnostic lab staff can search patient records using their Patient ID, upload verified reports, and initiate emergency break-glass sessions.
              </p>
              <ul className="text-sm text-slate-500 space-y-1">
                <li>• Verified organizational credential login</li>
                <li>• Direct verified diagnostic report upload</li>
                <li>• Audited Break-Glass emergency access workflow</li>
              </ul>
            </div>
            <div className="mt-8 pt-4 border-t border-slate-100">
              <Link
                href="/hospital/lookup"
                className="inline-flex w-full justify-center items-center px-4 py-2.5 rounded-lg bg-slate-900 text-white font-medium hover:bg-slate-800 transition"
              >
                Clinician & Hospital Login
              </Link>
            </div>
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div className="grid md:grid-cols-3 gap-6 pt-6">
          <div className="bg-white/80 rounded-xl p-5 border border-slate-200">
            <div className="flex items-center gap-3 text-slate-900 font-semibold mb-2">
              <QrCode className="w-5 h-5 text-blue-600" />
              <span>Zero-Install Sharing</span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Non-integrated doctors can scan an expiring QR code to view authorized documents on any phone or browser without installing apps or registering.
            </p>
          </div>

          <div className="bg-white/80 rounded-xl p-5 border border-slate-200">
            <div className="flex items-center gap-3 text-slate-900 font-semibold mb-2">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              <span>Break-Glass Emergency</span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              In trauma or unconscious states, verified medical personnel can access life-critical records with mandatory clinical justification and instant audit logging.
            </p>
          </div>

          <div className="bg-white/80 rounded-xl p-5 border border-slate-200">
            <div className="flex items-center gap-3 text-slate-900 font-semibold mb-2">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              <span>Zero Public Buckets</span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Medical files reside exclusively in private storage buckets. Access is mediated via short-lived signed URLs generated only after strict authorization checks.
            </p>
          </div>
        </div>

        {/* Status banner */}
        <footer className="text-center text-xs text-slate-500 pt-8 border-t border-slate-200">
          Phase 1 Architecture Foundation • Strictly Patient Medical Report Management
        </footer>
      </div>
    </main>
  );
}
