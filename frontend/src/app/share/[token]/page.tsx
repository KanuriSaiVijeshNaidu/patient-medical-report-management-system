import React from "react";
import { ShieldCheck, Clock, FileText, Download, AlertTriangle } from "lucide-react";

export default function SharedReportViewerPage({
  params,
}: {
  params: { token: string };
}) {
  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-bold">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900">Patient Authorized Share</h1>
                <p className="text-xs text-slate-500">Secure Zero-Install Medical Record Viewer</p>
              </div>
            </div>

            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-50 text-amber-800 text-xs font-medium border border-amber-200">
              <Clock className="w-3.5 h-3.5 text-amber-600" />
              <span>Time-Limited Access</span>
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-4 text-xs text-slate-600 space-y-1">
            <div><strong>Patient Reference:</strong> MED-2026-XXXXXX</div>
            <div><strong>Access Scope:</strong> Patient-Selected Records Only</div>
            <div><strong>Security Notice:</strong> Single-purpose cryptographic link. Revocable by patient at any moment.</div>
          </div>
        </div>

        {/* Reports Preview List */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-600" /> Authorized Medical Reports
          </h2>

          <div className="space-y-3">
            {/* Example item */}
            <div className="p-4 rounded-xl border border-slate-200 hover:border-slate-300 transition flex items-center justify-between gap-4">
              <div className="space-y-1">
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-100 text-blue-700">
                  Blood Test / Pathology
                </span>
                <h3 className="font-semibold text-slate-900 text-sm">Comprehensive Metabolic Panel</h3>
                <p className="text-xs text-slate-500">Test Date: 12 Oct 2026 • Verified Lab Report (PDF)</p>
              </div>

              <button
                type="button"
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg flex items-center gap-1.5 transition"
              >
                <Download className="w-4 h-4" /> View / Download
              </button>
            </div>
          </div>
        </div>

        {/* Confidentiality Footer */}
        <footer className="text-center text-xs text-slate-500">
          This digital health record is confidential and legally privileged. Unintended recipients must close this page immediately.
        </footer>
      </div>
    </div>
  );
}
