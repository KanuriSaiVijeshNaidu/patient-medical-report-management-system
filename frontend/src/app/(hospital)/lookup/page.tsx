import React from "react";
import { Search, UserCheck, ShieldAlert, FilePlus } from "lucide-react";

export default function HospitalLookupPage() {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Patient Record Lookup</h1>
        <p className="text-sm text-slate-600 mt-1">
          Search for an existing patient using their permanent unique Patient ID to view authorized records or upload diagnostic reports.
        </p>
      </div>

      {/* Lookup Form */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <label className="block text-sm font-semibold text-slate-700">
          Enter Patient ID (e.g., MED-YYYY-XXXXXX)
        </label>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="w-5 h-5 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="text"
              placeholder="MED-2026-XXXXXX"
              className="w-full pl-11 pr-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-slate-900"
            />
          </div>
          <button
            type="button"
            className="px-6 py-2.5 bg-slate-900 text-white font-medium rounded-lg hover:bg-slate-800 transition"
          >
            Search Record
          </button>
        </div>
      </div>

      {/* Identity Confirmation Pattern Preview */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
        <div className="flex items-center gap-2 text-slate-900 font-semibold border-b border-slate-100 pb-3">
          <UserCheck className="w-5 h-5 text-emerald-600" />
          <span>Patient Identity Confirmation Workflow</span>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed">
          Before clinical records or upload permissions are enabled, staff must confirm patient identity against date of birth and masked demographic credentials to prevent misfiling.
        </p>
        <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 text-xs font-mono text-slate-600 space-y-1">
          <div>Patient ID: MED-2026-XXXXXX</div>
          <div>Masked Name: R*** K***</div>
          <div>Gender: Female | Year of Birth: 1988</div>
          <div>Verified Phone Hash: Validated (Supabase Auth)</div>
        </div>
      </div>

      {/* Cross-hospital isolation note */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-800 flex items-start gap-2.5">
        <ShieldAlert className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
        <span>
          <strong>Data Leakage Prevention:</strong> Integrated hospital staff can only view reports issued by their own hospital organization, unless an active patient grant or emergency break-glass session is active.
        </span>
      </div>
    </div>
  );
}
